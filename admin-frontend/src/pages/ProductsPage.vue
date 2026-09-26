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
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>
      {{ notice }}
    </q-banner>

    <div v-if="selectedDrafts.length" class="q-mb-sm">
      <q-btn
        color="primary"
        icon="publish"
        :label="`Publier ${selectedDrafts.length} brouillon(s)`"
        no-caps
        :loading="publishing"
        data-testid="publish-selected"
        @click="publish(selectedDrafts.map((p) => p.id))"
      />
    </div>

    <q-table
      v-model:selected="selected"
      :rows="store.items"
      :columns="columns"
      row-key="id"
      :loading="store.loading"
      selection="multiple"
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
          <div class="text-body2 ellipsis" :title="props.row.name">
            <q-badge
              v-if="props.row.is_draft"
              color="orange-8"
              label="Brouillon"
              class="q-mr-xs"
              data-testid="product-draft-badge"
            />
            {{ props.row.name }}
          </div>
          <div class="text-caption text-grey-7">
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
          <q-btn
            v-if="props.row.is_draft"
            flat
            dense
            round
            icon="publish"
            color="orange-8"
            :loading="publishing"
            data-testid="product-publish"
            @click="publish([props.row.id])"
          >
            <q-tooltip>Publier (sortir du brouillon)</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            icon="history"
            color="grey-8"
            data-testid="product-price-history"
            @click="openHistory(props.row)"
          >
            <q-tooltip>Journal des prix</q-tooltip>
          </q-btn>
          <q-btn flat dense round icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <!-- Journal des prix -->
    <q-dialog v-model="historyOpen">
      <q-card style="min-width: 560px; max-width: 92vw">
        <q-card-section class="text-h6">
          Journal des prix — {{ historyProduct?.name }}
        </q-card-section>
        <q-card-section class="q-pt-none">
          <div class="text-caption text-grey-7 q-mb-sm">
            Chaque changement du prix de vente affiché en vitrine, avec sa cause : édition ou
            synchronisation de l'article, taux de change ou de taxe, marge de catégorie,
            paramètre de prix, recalcul nocturne.
          </div>
          <q-banner v-if="historyError" class="bg-red-1 text-red-9" dense rounded>{{
            historyError
          }}</q-banner>
          <div v-else-if="historyLoading" class="text-center q-pa-md">
            <q-spinner color="primary" size="2em" />
          </div>
          <div v-else-if="!history.length" class="text-grey-6 q-pa-md text-center">
            Aucun changement de prix enregistré.
          </div>
          <q-markup-table v-else dense flat bordered>
            <thead>
              <tr>
                <th class="text-left">Date</th>
                <th class="text-right">Ancien prix</th>
                <th class="text-right">Nouveau prix</th>
                <th class="text-left">Cause</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in history" :key="e.id">
                <td>{{ formatDateTime(e.created_at) }}</td>
                <td class="text-right">{{ e.old_price ?? '—' }}</td>
                <td class="text-right">{{ e.new_price ?? '—' }}</td>
                <td>{{ reasonLabel(e.reason) }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Fermer" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

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
import {
  useProductsStore,
  type ActiveFilter,
  type PriceHistoryEntry,
  type ProductPublic,
} from 'src/stores/products';
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
  { label: 'Inactifs', value: 'inactive' as const },
  { label: 'Brouillons (à publier)', value: 'draft' as const },
];

// --- Brouillons : publication unitaire ou en masse ------------------------
const selected = ref<ProductPublic[]>([]);
const selectedDrafts = computed(() => selected.value.filter((p) => p.is_draft));
const publishing = ref(false);
const notice = ref<string | null>(null);

// --- Journal des prix -------------------------------------------------------
const historyOpen = ref(false);
const historyProduct = ref<ProductPublic | null>(null);
const history = ref<PriceHistoryEntry[]>([]);
const historyLoading = ref(false);
const historyError = ref<string | null>(null);

const REASON_LABELS: Record<string, string> = {
  product_write: "Édition ou synchronisation de l'article",
  nightly: 'Recalcul nocturne (dates de validité)',
  admin_inline: 'Recalcul manuel',
  scheduled: 'Recalcul planifié',
  refresh: 'Recalcul',
};

function reasonLabel(reason: string): string {
  const [kind, detail] = reason.split(':', 2);
  if (kind === 'currency_rate') return `Taux de change ${detail ?? ''}`.trim();
  if (kind === 'system_setting') return `Paramètre de prix ${detail ?? ''}`.trim();
  if (kind?.startsWith('tax_rate')) return `Taux de taxe ${detail ?? ''}`.trim();
  if (kind?.startsWith('category')) return `Catégorie (${kind.replace('category_', '')})`;
  return REASON_LABELS[reason] ?? reason;
}

function formatDateTime(raw: string): string {
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleString('fr-FR');
}

async function openHistory(product: ProductPublic) {
  historyProduct.value = product;
  historyOpen.value = true;
  historyLoading.value = true;
  historyError.value = null;
  history.value = [];
  try {
    history.value = await store.priceHistory(product.id);
  } catch (err: unknown) {
    historyError.value = err instanceof Error ? err.message : 'Chargement impossible';
  } finally {
    historyLoading.value = false;
  }
}

async function publish(ids: string[]) {
  publishing.value = true;
  notice.value = null;
  try {
    const res = await store.publishProducts(ids);
    selected.value = [];
    notice.value = `${res.published} article(s) publié(s)${
      res.already_published ? `, ${res.already_published} déjà publié(s)` : ''
    }. La vitrine les montre dès qu'ils sont actifs, enrichis et tarifables.`;
  } catch (err: unknown) {
    store.error = err instanceof Error ? err.message : 'Publication impossible';
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
