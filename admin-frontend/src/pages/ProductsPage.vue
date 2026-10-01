<template>
  <q-page class="admin-page">
    <PageHeader
      title="Produits"
      hint="Articles du catalogue, manuels ou synchronisés depuis un fournisseur."
    >
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="store.loading"
          @click="store.fetchPage()"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau produit"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-input
        v-model="searchInput"
        label="Rechercher (nom, SKU, MPN)"
        outlined
        dense
        clearable
        debounce="300"
        style="min-width: 320px"
        @update:model-value="onSearchChange"
      >
        <template #prepend>
          <q-icon name="ph:magnifying-glass" />
        </template>
      </q-input>
      <q-select
        v-model="activeFilter"
        :options="filterOptions"
        label="Statut"
        outlined
        dense
        emit-value
        map-options
        style="min-width: 260px"
        @update:model-value="onFilterChange"
      />
      <q-select
        v-model="sort"
        :options="sortOptions"
        label="Trier par"
        outlined
        dense
        emit-value
        map-options
        style="min-width: 220px"
        data-testid="products-sort"
        @update:model-value="onSortChange"
      />
    </div>

    <div v-if="store.error || notice" class="admin-notices">
      <AppNotice v-if="store.error" tone="error" dense>{{ store.error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div v-if="selected.length" class="admin-toolbar">
      <span class="text-body2">{{ selected.length }} article(s) sélectionné(s)</span>
      <q-btn
        v-if="selectedDrafts.length"
        color="primary"
        unelevated
        no-caps
        icon="ph:upload-simple"
        :label="`Publier ${selectedDrafts.length} brouillon(s)`"
        :loading="publishing"
        data-testid="publish-selected"
        @click="publish(selectedDrafts.map((p) => p.id))"
      />
      <q-btn
        :unelevated="!selectedDrafts.length"
        :outline="!!selectedDrafts.length"
        color="primary"
        no-caps
        icon="ph:eye"
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
        no-caps
        icon="ph:eye-slash"
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
            no-spinner
            fit="contain"
            class="product-thumb"
          >
            <template #error>
              <div class="absolute-full flex flex-center product-thumb__fallback">
                <q-icon name="ph:image-broken" class="text-subtle" />
              </div>
            </template>
          </q-img>
        </q-td>
      </template>

      <template #body-cell-name="props">
        <q-td :props="props">
          <div class="text-body2 ellipsis" :title="props.row.name">
            <StatusTag
              v-if="props.row.is_draft"
              label="Brouillon"
              tone="warn"
              icon="ph:pencil-simple"
              class="q-mr-xs"
              data-testid="product-draft-badge"
            />
            {{ props.row.name }}
          </div>
          <div class="text-caption text-muted">
            <q-chip
              v-if="props.row.has_variants"
              dense
              size="sm"
              icon="ph:stack"
              :label="`${props.row.variants_count ?? 0} variante(s)`"
            />
            <q-chip
              v-else-if="props.row.parent_product_id"
              dense
              size="sm"
              :label="variantLabel(props.row)"
            />
            {{ props.row.manufacturer || '—' }}
            <q-icon
              v-if="props.row.overridden_fields?.length"
              name="ph:lock"
              size="xs"
              class="q-ml-xs text-warning"
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

      <template #body-cell-price="props">
        <q-td :props="props" class="font-mono text-right">
          {{ money(props.row.sale_price_cached) }}
        </q-td>
      </template>

      <template #body-cell-cost="props">
        <q-td :props="props" class="font-mono text-right">
          {{ money(props.row.unit_cost_cached) }}
        </q-td>
      </template>

      <template #body-cell-margin="props">
        <q-td :props="props" class="text-right" data-testid="product-margin">
          <template v-if="props.row.margin_cached != null">
            <div
              class="font-mono"
              :class="{ 'text-negative': Number(props.row.margin_cached) < 0 }"
            >
              {{ money(props.row.margin_cached) }}
            </div>
            <div class="text-caption text-subtle">{{ pct(props.row.margin_pct_cached) }}</div>
          </template>
          <span v-else class="text-subtle">
            —
            <q-tooltip>Coût d'achat inconnu</q-tooltip>
          </span>
        </q-td>
      </template>

      <template #body-cell-storefront="props">
        <q-td :props="props" align="center">
          <span v-if="isVisible(props.row)">
            <StatusTag
              :label="props.row.published_without_enrichment ? 'Publié tel quel' : 'Visible'"
              :tone="props.row.published_without_enrichment ? 'warn' : 'ok'"
              icon="ph:eye"
            />
            <q-tooltip v-if="props.row.published_without_enrichment">
              Affiché sans enrichissement Icecat, sur décision admin
            </q-tooltip>
          </span>
          <span v-else>
            <StatusTag label="Masqué" tone="neutral" icon="ph:eye-slash" />
            <q-tooltip>
              Ligne fournisseur en attente d'enrichissement Icecat : invisible en boutique.
              Sélectionnez-la et « Publier tel quel » pour l'afficher.
            </q-tooltip>
          </span>
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
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn
            v-if="props.row.is_draft"
            flat
            dense
            round
            icon="ph:upload-simple"
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
            icon="ph:clock-counter-clockwise"
            data-testid="product-price-history"
            @click="openHistory(props.row)"
          >
            <q-tooltip>Journal des prix</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            icon="ph:pencil-simple"
            aria-label="Modifier"
            @click="openEdit(props.row)"
          >
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>

      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucun produit.</div>
      </template>
    </q-table>

    <!-- Journal des prix -->
    <q-dialog v-model="historyOpen">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Journal des prix — {{ historyProduct?.name }}</h2>
          <p class="app-dialog__text">
            Chaque changement du prix de vente affiché en vitrine, avec sa cause : édition ou
            synchronisation de l'article, taux de change ou de taxe, marge de catégorie, paramètre
            de prix, recalcul nocturne.
          </p>
        </q-card-section>
        <q-card-section>
          <AppNotice v-if="historyError" tone="error" dense>{{ historyError }}</AppNotice>
          <div v-else-if="historyLoading" class="text-center q-pa-md">
            <q-spinner size="2em" />
          </div>
          <div v-else-if="!history.length" class="text-subtle q-pa-md text-center">
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
                <td class="text-right font-mono">{{ e.old_price ?? '—' }}</td>
                <td class="text-right font-mono">{{ e.new_price ?? '—' }}</td>
                <td>{{ reasonLabel(e.reason) }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Fermer" v-close-popup />
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
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { formatMoney, intlLocale } from '@app/utils';
import { useShopConfigStore } from '@/stores/shopConfig';
import {
  useProductsStore,
  type ActiveFilter,
  type PriceHistoryEntry,
  type ProductSort,
  type ProductPublic,
} from '@/stores/products';
import { listPlaces, type Place } from '@/api/logistics';
import ProductFormDialog from '@/components/ProductFormDialog.vue';

const store = useProductsStore();
const shopConfig = useShopConfigStore();

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

const sort = ref<ProductSort>(store.sort);
const sortOptions: { label: string; value: ProductSort }[] = [
  { label: 'Plus récents', value: '' },
  { label: 'Marge HT décroissante', value: 'margin_desc' },
  { label: 'Marge HT croissante', value: 'margin_asc' },
  { label: 'Taux de marque décroissant', value: 'margin_pct_desc' },
  { label: 'Taux de marque croissant', value: 'margin_pct_asc' },
  { label: 'Prix décroissant', value: 'price_desc' },
  { label: 'Prix croissant', value: 'price_asc' },
  { label: 'Coût décroissant', value: 'cost_desc' },
];

function onSortChange(value: ProductSort) {
  store.applyFilters({ sort: value ?? '' });
  currentPage.value = 1;
}

function money(value: string | null | undefined): string {
  return value == null ? '—' : formatMoney(value, shopConfig.currency);
}

function pct(value: string | null | undefined): string {
  return value == null
    ? '—'
    : `${Number(value).toLocaleString(intlLocale(), { maximumFractionDigits: 1 })} %`;
}

const filterOptions = [
  { label: 'Tous', value: 'all' as const },
  { label: 'Actifs', value: 'active' as const },
  { label: 'Enrichis', value: 'enriched' as const },
  { label: 'Masqués (en attente d’enrichissement)', value: 'hidden' as const },
  { label: 'Inactifs', value: 'inactive' as const },
  { label: 'Brouillons (à publier)', value: 'draft' as const },
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

// --- Brouillons : publication unitaire ou en masse ------------------------
const selectedDrafts = computed(() => selected.value.filter((p) => p.is_draft));
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
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleString(intlLocale());
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
    const res = await store.publishDrafts(ids);
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
    classes: 'font-mono',
  },
  { name: 'name', label: 'Nom', field: 'name', align: 'left', style: 'max-width: 480px' },
  {
    name: 'origin',
    label: 'Origine (fournisseur)',
    field: 'supplier_place_id',
    align: 'left',
  },
  { name: 'price', label: 'Prix TTC', field: 'sale_price_cached', align: 'right' },
  { name: 'cost', label: 'Coût HT', field: 'unit_cost_cached', align: 'right' },
  { name: 'margin', label: 'Marge HT', field: 'margin_cached', align: 'right' },
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

<style scoped lang="scss">
.product-thumb {
  border-radius: 6px;
}

.product-thumb__fallback {
  background: var(--n-tile);
}
</style>
