<template>
  <q-page padding>
    <div class="row q-col-gutter-md q-mb-md items-end">
      <div class="col-12 col-md-5">
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
      <div class="col-12 col-md-3 text-right">
        <q-btn
          unelevated
          color="primary"
          icon="add"
          label="Nouveau"
          class="q-mr-sm"
          @click="openCreate"
        />
        <q-btn
          flat
          icon="refresh"
          label="Actualiser"
          :loading="store.loading"
          @click="store.fetchPage()"
        />
      </div>
    </div>

    <q-banner v-if="store.error" class="bg-negative text-white q-mb-md" dense>
      {{ store.error }}
    </q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>
      {{ notice }}
    </q-banner>

    <div v-if="selected.length" class="row items-center q-gutter-sm q-mb-sm">
      <span class="text-body2">{{ selected.length }} article(s) sélectionné(s)</span>
      <q-btn
        unelevated
        color="primary"
        icon="visibility"
        label="Publier tel quel"
        :loading="publishing"
        @click="publishSelected(true)"
      >
        <q-tooltip>
          Afficher en boutique sans attendre l'enrichissement Icecat (qui pourra toujours compléter
          la fiche ensuite)
        </q-tooltip>
      </q-btn>
      <q-btn
        flat
        color="grey-8"
        icon="visibility_off"
        label="Remettre en attente"
        :loading="publishing"
        @click="publishSelected(false)"
      />
    </div>

    <q-table
      v-model:selected="selected"
      :rows="store.items"
      :columns="columns"
      row-key="id"
      selection="multiple"
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
            <q-chip
              v-if="props.row.has_variants"
              dense
              size="sm"
              color="teal-2"
              text-color="teal-10"
              :label="`${props.row.variants_count ?? 0} variante(s)`"
            />
            <q-chip
              v-else-if="props.row.parent_product_id"
              dense
              size="sm"
              color="grey-3"
              text-color="grey-8"
              :label="variantLabel(props.row)"
            />
            {{ props.row.manufacturer || '—' }}
            <q-icon
              v-if="props.row.overridden_fields?.length"
              name="lock"
              color="orange-8"
              size="xs"
              class="q-ml-xs"
            >
              <q-tooltip>
                {{ props.row.overridden_fields.length }} champ(s) verrouillé(s) contre la
                synchronisation
              </q-tooltip>
            </q-icon>
          </div>
        </q-td>
      </template>

      <template #body-cell-origin="props">
        <q-td :props="props">
          <q-select
            :model-value="props.row.supplier_place_id ?? null"
            :options="placeOptions"
            dense
            outlined
            options-dense
            emit-value
            map-options
            clearable
            hide-bottom-space
            placeholder="—"
            style="min-width: 200px"
            :disable="store.savingOriginIds.has(props.row.id)"
            :loading="store.savingOriginIds.has(props.row.id)"
            @update:model-value="(val) => onOriginChange(props.row, val)"
          />
        </q-td>
      </template>

      <template #body-cell-storefront="props">
        <q-td :props="props" align="center">
          <q-chip
            v-if="isVisible(props.row)"
            dense
            size="sm"
            :color="props.row.published_without_enrichment ? 'orange-2' : 'green-2'"
            :text-color="props.row.published_without_enrichment ? 'orange-10' : 'green-10'"
            :label="props.row.published_without_enrichment ? 'Publié tel quel' : 'Visible'"
          >
            <q-tooltip v-if="props.row.published_without_enrichment">
              Affiché sans enrichissement Icecat, sur décision admin
            </q-tooltip>
          </q-chip>
          <q-chip v-else dense size="sm" color="grey-3" text-color="grey-8" label="Masqué">
            <q-tooltip>
              Ligne fournisseur en attente d'enrichissement Icecat : invisible en boutique.
              Sélectionnez-la et « Publier tel quel » pour l'afficher.
            </q-tooltip>
          </q-chip>
        </q-td>
      </template>

      <template #body-cell-active="props">
        <q-td :props="props" align="center">
          <q-toggle
            :model-value="props.row.is_admin_active"
            color="positive"
            :disable="store.togglingIds.has(props.row.id)"
            @update:model-value="store.toggleActive(props.row)"
          />
        </q-td>
      </template>

      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense round icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <ProductFormDialog v-model="formOpen" :product="editingProduct" @saved="store.fetchPage()" />

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
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { useProductsStore, type ActiveFilter, type ProductPublic } from 'src/stores/products';
import { listPlaces, type Place } from 'src/api/logistics';
import ProductFormDialog from 'src/components/ProductFormDialog.vue';

const store = useProductsStore();

const formOpen = ref(false);
const editingProduct = ref<ProductPublic | null>(null);

function openCreate() {
  editingProduct.value = null;
  formOpen.value = true;
}
function openEdit(product: ProductPublic) {
  editingProduct.value = product;
  formOpen.value = true;
}
const searchInput = ref(store.search);
const activeFilter = ref<ActiveFilter>(store.activeFilter);
const currentPage = ref(store.page);

const places = ref<Place[]>([]);
const placeOptions = computed(() =>
  places.value.map((p) => ({ label: p.code ? `${p.name} (${p.code})` : p.name, value: p.id })),
);

function onOriginChange(product: Parameters<typeof store.updateOriginPlace>[0], value: unknown) {
  void store.updateOriginPlace(product, typeof value === 'string' ? value : null);
}

const placeholderImg =
  'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"/>';

const filterOptions = [
  { label: 'Tous', value: 'all' as const },
  { label: 'Actifs', value: 'active' as const },
  { label: 'Enrichis', value: 'enriched' as const },
  { label: 'Masqués (en attente d’enrichissement)', value: 'hidden' as const },
  { label: 'Inactifs', value: 'inactive' as const },
];

const selected = ref<ProductPublic[]>([]);

function variantLabel(product: ProductPublic): string {
  const options = Object.entries(product.variant_options ?? {}).map(([k, v]) => `${k} ${v}`);
  return options.length ? `Variante · ${options.join(' / ')}` : 'Variante';
}
const publishing = ref(false);
const notice = ref<string | null>(null);

/** Same rule as the storefront: enriched, or manual, or published as it stands. */
function isVisible(product: ProductPublic): boolean {
  return (
    Boolean(product.is_enriched) ||
    !product.is_supplier_managed ||
    Boolean(product.published_without_enrichment)
  );
}

async function publishSelected(published: boolean) {
  if (!selected.value.length) return;
  publishing.value = true;
  notice.value = null;
  try {
    const updated = await store.publishProducts(
      selected.value.map((p) => p.id),
      published,
    );
    notice.value = published
      ? `${updated} article(s) publié(s) tel(s) quel(s).`
      : `${updated} article(s) remis en attente d’enrichissement.`;
    selected.value = [];
  } catch (err: unknown) {
    store.error = err instanceof Error ? err.message : 'Publication impossible.';
  } finally {
    publishing.value = false;
  }
}

const columns: QTableColumn[] = [
  { name: 'image', label: '', field: 'image_url', align: 'left' },
  {
    name: 'sku',
    label: 'SKU',
    field: (row) => row.supplier_sku || row.vendor_part_number || '—',
    align: 'left',
  },
  { name: 'name', label: 'Nom', field: 'name', align: 'left', style: 'max-width: 480px' },
  {
    name: 'origin',
    label: 'Origine (fournisseur)',
    field: 'supplier_place_id',
    align: 'left',
  },
  { name: 'storefront', label: 'Vitrine', field: 'is_enriched', align: 'center' },
  { name: 'active', label: 'Actif admin', field: 'is_admin_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

const totalPages = computed(() => Math.max(1, Math.ceil(store.totalCount / store.pageSize)));

function onSearchChange(value: string | number | null) {
  store.applyFilters({ search: value == null ? '' : String(value) });
  currentPage.value = 1;
}

function onFilterChange(value: ActiveFilter) {
  store.applyFilters({ activeFilter: value });
  currentPage.value = 1;
}

onMounted(() => {
  void store.fetchPage();
  void loadPlaces();
});

async function loadPlaces() {
  try {
    places.value = await listPlaces();
  } catch {
    // Non-blocking: the origin selector simply stays empty if places fail to load.
  }
}
</script>
