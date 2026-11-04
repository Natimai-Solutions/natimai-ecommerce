<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('products.title')" :hint="$t('products.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="store.loading"
          @click="store.fetchPage()"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('products.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-input
        v-model="searchInput"
        :label="$t('products.search')"
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
        :label="$t('common.status')"
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
        :label="$t('products.sort')"
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
      <span class="text-body2">{{ $t('products.n_selected', { n: selected.length }) }}</span>
      <q-btn
        v-if="selectedDrafts.length"
        color="primary"
        unelevated
        no-caps
        icon="ph:upload-simple"
        :label="$t('products.publish_n', { n: selectedDrafts.length })"
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
        :label="$t('products.publish_as_is')"
        :loading="publishing"
        @click="publishSelected(true)"
      >
        <q-tooltip>
          {{ $t('products.publish_as_is_hint') }}
        </q-tooltip>
      </q-btn>
      <q-btn
        flat
        no-caps
        icon="ph:eye-slash"
        :label="$t('products.back_pending')"
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
              :label="$t('products.draft')"
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
              :label="$t('products.n_variants', { n: props.row.variants_count ?? 0 })"
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
                {{ $t('products.locked', { n: props.row.overridden_fields.length }) }}
              </q-tooltip>
            </q-icon>
          </div>
        </q-td>
      </template>

      <template #body-cell-origin="props">
        <q-td :props="props">
          <q-select
            :aria-label="`${$t('products.col_origin')} — ${props.row.name}`"
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
            <q-tooltip>{{ $t('products.unknown_cost') }}</q-tooltip>
          </span>
        </q-td>
      </template>

      <template #body-cell-storefront="props">
        <q-td :props="props" align="center">
          <span v-if="isVisible(props.row)">
            <StatusTag
              :label="
                props.row.published_without_enrichment
                  ? $t('products.published_as_is')
                  : $t('products.visible')
              "
              :tone="props.row.published_without_enrichment ? 'warn' : 'ok'"
              icon="ph:eye"
            />
            <q-tooltip v-if="props.row.published_without_enrichment">
              {{ $t('products.shown_as_is') }}
            </q-tooltip>
          </span>
          <span v-else>
            <StatusTag :label="$t('products.hidden')" tone="neutral" icon="ph:eye-slash" />
            <q-tooltip>
              {{ $t('products.pending_hint') }}
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
            <q-tooltip>{{ $t('products.publish') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            icon="ph:clock-counter-clockwise"
            data-testid="product-price-history"
            @click="openHistory(props.row)"
          >
            <q-tooltip>{{ $t('products.price_log') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            round
            icon="ph:pencil-simple"
            :aria-label="$t('products.edit_aria')"
            @click="openEdit(props.row)"
          >
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="!props.row.parent_product_id"
            flat
            dense
            round
            icon="ph:copy"
            :aria-label="$t('products.duplicate')"
            data-testid="product-duplicate"
            @click="openDuplicate(props.row)"
          >
            <q-tooltip>{{ $t('products.duplicate_tip') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>

      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('products.none') }}</div>
      </template>
    </q-table>

    <!-- Journal des prix -->
    <q-dialog v-model="historyOpen">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('products.price_log_of', { name: historyProduct?.name }) }}
          </h2>
          <p class="app-dialog__text">
            {{ $t('products.price_log_hint') }}
          </p>
        </q-card-section>
        <q-card-section>
          <AppNotice v-if="historyError" tone="error" dense>{{ historyError }}</AppNotice>
          <div v-else-if="historyLoading" class="text-center q-pa-md">
            <q-spinner size="2em" />
          </div>
          <div v-else-if="!history.length" class="text-subtle q-pa-md text-center">
            {{ $t('products.no_change') }}
          </div>
          <q-markup-table v-else dense flat bordered>
            <thead>
              <tr>
                <th class="text-left">{{ $t('products.h_date') }}</th>
                <th class="text-right">{{ $t('products.h_old') }}</th>
                <th class="text-right">{{ $t('products.h_new') }}</th>
                <th class="text-left">{{ $t('products.h_cause') }}</th>
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
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <ProductFormDialog
      v-model="formOpen"
      :product="editingProduct"
      :duplicate-of="duplicateSource"
      @saved="store.fetchPage()"
    />

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
import { useI18n } from 'vue-i18n';
import { labels } from '@/i18n/global';
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

const { t } = useI18n();

const store = useProductsStore();
const shopConfig = useShopConfigStore();

const formOpen = ref(false);
const editingProduct = ref<ProductPublic | null>(null);
/** Article dont « Dupliquer » pré-remplit le formulaire de création. */
const duplicateSource = ref<ProductPublic | null>(null);

function openCreate() {
  editingProduct.value = null;
  duplicateSource.value = null;
  formOpen.value = true;
}
function openEdit(product: ProductPublic) {
  editingProduct.value = product;
  duplicateSource.value = null;
  formOpen.value = true;
}
/** Nouveau produit pré-rempli depuis `product` ; l'original n'est pas touché. */
function openDuplicate(product: ProductPublic) {
  editingProduct.value = null;
  duplicateSource.value = product;
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
const sortOptions = computed<{ label: string; value: ProductSort }[]>(() => [
  { label: t('products.s_recent'), value: '' },
  { label: t('products.s_margin_desc'), value: 'margin_desc' },
  { label: t('products.s_margin_asc'), value: 'margin_asc' },
  { label: t('products.s_rate_desc'), value: 'margin_pct_desc' },
  { label: t('products.s_rate_asc'), value: 'margin_pct_asc' },
  { label: t('products.s_price_desc'), value: 'price_desc' },
  { label: t('products.s_price_asc'), value: 'price_asc' },
  { label: t('products.s_cost_desc'), value: 'cost_desc' },
]);

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
  { label: t('products.f_all'), value: 'all' as const },
  { label: t('products.f_active'), value: 'active' as const },
  { label: t('products.f_enriched'), value: 'enriched' as const },
  { label: t('products.f_hidden'), value: 'hidden' as const },
  { label: t('products.f_inactive'), value: 'inactive' as const },
  { label: t('products.f_drafts'), value: 'draft' as const },
];

const selected = ref<ProductPublic[]>([]);

function variantLabel(product: ProductPublic): string {
  const options = Object.entries(product.variant_options ?? {}).map(([k, v]) => `${k} ${v}`);
  return options.length
    ? t('products.variant_of', { options: options.join(' / ') })
    : t('products.variant');
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
    store.error = err instanceof Error ? err.message : t('products.publish_failed');
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

const REASON_LABELS: Record<string, string> = labels({
  product_write: 'products.r_product',
  nightly: 'products.r_nightly',
  admin_inline: 'products.r_manual',
  scheduled: 'products.r_scheduled',
  refresh: 'products.r_refresh',
});

function reasonLabel(reason: string): string {
  const [kind, detail] = reason.split(':', 2);
  if (kind === 'currency_rate') return t('products.r_currency', { detail: detail ?? '' }).trim();
  if (kind === 'system_setting') return t('products.r_setting', { detail: detail ?? '' }).trim();
  if (kind?.startsWith('tax_rate')) return t('products.r_tax', { detail: detail ?? '' }).trim();
  if (kind?.startsWith('category'))
    return t('products.r_category', { kind: kind.replace('category_', '') });
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
    historyError.value = err instanceof Error ? err.message : t('common.load_failed');
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
    notice.value = t('products.published_n', {
      n: res.published,
      already: res.already_published ? t('products.already_n', { n: res.already_published }) : '',
    });
  } catch (err: unknown) {
    store.error = err instanceof Error ? err.message : t('products.publish_failed');
  } finally {
    publishing.value = false;
  }
}

const columns = computed<QTableColumn[]>(() => [
  { name: 'image', label: '', field: 'image_url', align: 'left' },
  {
    name: 'sku',
    label: t('products.col_sku'),
    field: (row) => row.supplier_sku || row.vendor_part_number || '—',
    align: 'left',
    classes: 'font-mono',
  },
  {
    name: 'name',
    label: t('products.col_name'),
    field: 'name',
    align: 'left',
    style: 'max-width: 480px',
  },
  {
    name: 'origin',
    label: t('products.col_origin'),
    field: 'supplier_place_id',
    align: 'left',
  },
  { name: 'price', label: t('products.col_price'), field: 'sale_price_cached', align: 'right' },
  { name: 'cost', label: t('products.col_cost'), field: 'unit_cost_cached', align: 'right' },
  { name: 'margin', label: t('products.col_margin'), field: 'margin_cached', align: 'right' },
  { name: 'storefront', label: t('products.col_shop'), field: 'is_enriched', align: 'center' },
  { name: 'active', label: t('products.col_active'), field: 'is_admin_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

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
