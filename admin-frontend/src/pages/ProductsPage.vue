<template>
  <q-page padding>
    <div class="row q-col-gutter-md q-mb-md items-end">
      <div class="col-12 col-md-6">
        <q-input
          v-model="searchInput"
          label="Rechercher (nom, SKU, MPN)"
          outlined
          dense
          clearable
          debounce="300"
          @update:model-value="onSearchChange"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </div>
      <div class="col-12 col-md-4">
        <q-select
          v-model="activeFilter"
          :options="filterOptions"
          label="Statut"
          outlined
          dense
          emit-value
          map-options
          @update:model-value="onFilterChange"
        />
      </div>
      <div class="col-12 col-md-2 text-right">
        <q-btn flat icon="refresh" label="Actualiser" :loading="store.loading" @click="store.fetchPage()" />
      </div>
    </div>

    <q-banner v-if="store.error" class="bg-negative text-white q-mb-md" dense>
      {{ store.error }}
    </q-banner>

    <q-table
      :rows="store.items"
      :columns="columns"
      row-key="id"
      :loading="store.loading"
      flat
      bordered
      hide-pagination
      :rows-per-page-options="[0]"
    >
      <template #body-cell-image="props">
        <q-td :props="props">
          <q-img
            :src="props.row.image_url || props.row.supplier_image_url || placeholderImg"
            :ratio="1"
            width="48px"
            spinner-color="primary"
            no-spinner
            fit="contain"
          >
            <template #error>
              <div class="absolute-full flex flex-center bg-grey-3">
                <q-icon name="image_not_supported" color="grey-6" />
              </div>
            </template>
          </q-img>
        </q-td>
      </template>

      <template #body-cell-name="props">
        <q-td :props="props">
          <div class="text-body2 ellipsis" :title="props.row.name">{{ props.row.name }}</div>
          <div class="text-caption text-grey-7">
            {{ props.row.manufacturer || '—' }}
          </div>
        </q-td>
      </template>

      <template #body-cell-active="props">
        <q-td :props="props" align="center">
          <q-toggle
            :model-value="props.row.is_active"
            color="positive"
            :disable="store.togglingIds.has(props.row.id)"
            @update:model-value="store.toggleActive(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <div class="row justify-end q-mt-md">
      <q-pagination
        v-model="currentPage"
        :max="totalPages"
        :max-pages="6"
        boundary-numbers
        @update:model-value="store.setPage($event)"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { useProductsStore, type ActiveFilter } from 'src/stores/products'

const store = useProductsStore()
const searchInput = ref(store.search)
const activeFilter = ref<ActiveFilter>(store.activeFilter)
const currentPage = ref(store.page)

const placeholderImg =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"/>'

const filterOptions = [
  { label: 'Tous', value: 'all' as const },
  { label: 'Actifs', value: 'active' as const },
  { label: 'Enrichis', value: 'enriched' as const },
  { label: 'Inactifs', value: 'inactive' as const },
]

const columns: QTableColumn[] = [
  { name: 'image', label: '', field: 'image_url', align: 'left' },
  { name: 'sku', label: 'SKU', field: (row) => row.supplier_sku || row.vendor_part_number || '—', align: 'left' },
  { name: 'name', label: 'Nom', field: 'name', align: 'left', style: 'max-width: 480px' },
  { name: 'active', label: 'Actif', field: 'is_active', align: 'center' },
]

const totalPages = computed(() => Math.max(1, Math.ceil(store.totalCount / store.pageSize)))

function onSearchChange(value: string | number | null) {
  store.applyFilters({ search: value == null ? '' : String(value) })
  currentPage.value = 1
}

function onFilterChange(value: ActiveFilter) {
  store.applyFilters({ activeFilter: value })
  currentPage.value = 1
}

onMounted(() => {
  void store.fetchPage()
})
</script>
