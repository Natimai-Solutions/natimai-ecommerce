<template>
  <q-page class="catalogue page-container">
    <!-- Catégories -->
    <nav
      v-if="categoryOptions.length > 0"
      class="catalogue__cats"
      :aria-label="$t('catalogue.categories')"
    >
      <button
        type="button"
        class="chip"
        :class="{ 'chip--active': selectedCategory === null }"
        :aria-pressed="selectedCategory === null"
        @click="onCategoryChange(null)"
      >
        {{ $t('catalogue.all') }}
      </button>
      <button
        v-for="cat in categoryOptions"
        :key="cat.value"
        type="button"
        class="chip"
        :class="{ 'chip--active': selectedCategory === cat.value }"
        :aria-pressed="selectedCategory === cat.value"
        @click="onCategoryChange(cat.value)"
      >
        {{ cat.label }}
      </button>
    </nav>

    <div class="catalogue__layout">
      <!-- Filtres : colonne sur ordinateur, panneau plein écran sur mobile -->
      <aside
        id="catalogue-filters"
        class="filters"
        :class="{ 'filters--open': filtersOpen }"
        :aria-label="$t('catalogue.filters')"
      >
        <div class="filters__sheet-head">
          <span class="filters__sheet-title">{{ $t('catalogue.filters') }}</span>
          <q-btn
            flat
            round
            icon="ph:x"
            :aria-label="$t('catalogue.close_filters')"
            @click="filtersOpen = false"
          />
        </div>

        <div class="filters__body">
          <div class="filters__group">
            <fieldset class="filters__fieldset" data-testid="catalogue-stock">
              <legend class="filters__legend">{{ $t('catalogue.availability') }}</legend>
              <label v-for="opt in stockOptions" :key="String(opt.value)" class="filters__option">
                <input
                  type="radio"
                  name="stock"
                  :checked="selectedStock === opt.value"
                  :data-testid="`catalogue-stock-${opt.value ?? 'all'}`"
                  @change="onStockChange(opt.value)"
                />
                <span class="filters__option-label">{{ opt.label }}</span>
                <span v-if="opt.count != null" class="filters__count font-mono">{{
                  opt.count
                }}</span>
              </label>
            </fieldset>
          </div>

          <div class="filters__group">
            <fieldset class="filters__fieldset" data-testid="catalogue-condition">
              <legend class="filters__legend">{{ $t('catalogue.condition') }}</legend>
              <label
                v-for="opt in conditionOptions"
                :key="String(opt.value)"
                class="filters__option"
              >
                <input
                  type="radio"
                  name="condition"
                  :checked="selectedCondition === opt.value"
                  :data-testid="`catalogue-condition-${opt.value ?? 'all'}`"
                  @change="onConditionChange(opt.value)"
                />
                <span class="filters__option-label">{{ opt.label }}</span>
                <span v-if="opt.count != null" class="filters__count font-mono">{{
                  opt.count
                }}</span>
              </label>
            </fieldset>
          </div>

          <div v-if="manufacturerOptions.length > 0" class="filters__group">
            <fieldset class="filters__fieldset">
              <legend class="filters__legend">{{ $t('catalogue.manufacturer') }}</legend>
              <label class="filters__option">
                <input
                  type="radio"
                  name="manufacturer"
                  :checked="selectedManufacturer === null"
                  @change="onManufacturerChange(null)"
                />
                <span class="filters__option-label">{{ $t('catalogue.all_manufacturers') }}</span>
              </label>
              <label v-for="opt in visibleManufacturers" :key="opt.value" class="filters__option">
                <input
                  type="radio"
                  name="manufacturer"
                  :checked="selectedManufacturer === opt.value"
                  @change="onManufacturerChange(opt.value)"
                />
                <span class="filters__option-label">{{ opt.value }}</span>
                <span class="filters__count font-mono">{{ opt.count }}</span>
              </label>
              <button
                v-if="hiddenManufacturerCount > 0"
                type="button"
                class="text-link filters__more"
                @click="showAllManufacturers = true"
              >
                {{ $t('catalogue.more_manufacturers', { n: hiddenManufacturerCount }) }}
              </button>
            </fieldset>
          </div>

          <template v-for="facet in store.specFacets" :key="facet.key">
            <div v-if="facet.type === 'numeric'" class="filters__group">
              <label :for="`spec-${facet.key}`" class="filters__legend">
                {{ $t('catalogue.spec_min', { label: facet.label_fr }) }}
              </label>
              <select
                :id="`spec-${facet.key}`"
                class="field-input"
                :value="numericMin[facet.key] ?? ''"
                @change="onNumericSelect(facet.key, $event)"
              >
                <option value="">{{ $t('catalogue.any') }}</option>
                <option v-for="opt in numericOptions(facet)" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>

            <div v-else class="filters__group">
              <fieldset class="filters__fieldset">
                <legend class="filters__legend">{{ facet.label_fr }}</legend>
                <label
                  v-for="val in facet.values ?? []"
                  :key="String(val.value_text)"
                  class="filters__option"
                >
                  <input
                    type="checkbox"
                    :checked="(enumSelections[facet.key] ?? []).includes(val.value_text ?? '')"
                    @change="
                      onEnumToggle(
                        facet.key,
                        val.value_text ?? '',
                        ($event.target as HTMLInputElement).checked,
                      )
                    "
                  />
                  <span class="filters__option-label">{{ val.value_text }}</span>
                  <span class="filters__count font-mono">{{ val.count }}</span>
                </label>
              </fieldset>
            </div>
          </template>

          <form class="filters__group" @submit.prevent="onPriceChange">
            <span class="filters__legend">{{
              $t('catalogue.price', { currency: currencyStore.reference })
            }}</span>
            <div class="filters__price">
              <div class="field">
                <label for="price-min" class="field__label">{{ $t('catalogue.min') }}</label>
                <input
                  id="price-min"
                  v-model.number="priceMin"
                  type="number"
                  min="0"
                  inputmode="numeric"
                  class="field-input font-mono"
                />
              </div>
              <div class="field">
                <label for="price-max" class="field__label">{{ $t('catalogue.max') }}</label>
                <input
                  id="price-max"
                  v-model.number="priceMax"
                  type="number"
                  min="0"
                  inputmode="numeric"
                  class="field-input font-mono"
                />
              </div>
            </div>
            <q-btn
              type="submit"
              outline
              color="primary"
              :label="$t('catalogue.apply')"
              class="filters__apply"
            />
          </form>

          <button type="button" class="text-link filters__reset" @click="resetFilters">
            {{ $t('catalogue.reset') }}
          </button>
        </div>

        <div class="filters__sheet-foot">
          <q-btn
            unelevated
            color="primary"
            class="full-width"
            :label="$t('catalogue.see_results', { label: resultLabel })"
            @click="filtersOpen = false"
          />
        </div>
      </aside>

      <section class="catalogue__results" aria-labelledby="catalogue-title">
        <div class="catalogue__head">
          <div class="catalogue__heading">
            <h1 id="catalogue-title" class="page-title">{{ pageTitle }}</h1>
            <span v-if="!store.loading && !store.error" class="catalogue__count font-mono">
              {{ resultLabel }}
            </span>
          </div>
          <q-btn
            outline
            color="primary"
            icon="ph:sliders-horizontal"
            :label="
              activeFilters.length > 0
                ? $t('catalogue.filters_n', { n: activeFilters.length })
                : $t('catalogue.filters')
            "
            class="lt-md"
            aria-controls="catalogue-filters"
            :aria-expanded="filtersOpen"
            @click="filtersOpen = true"
          />
        </div>

        <div v-if="activeFilters.length > 0" class="catalogue__active">
          <button
            v-for="f in activeFilters"
            :key="f.key"
            type="button"
            class="active-filter"
            :aria-label="$t('catalogue.remove_filter', { label: f.label })"
            @click="f.remove()"
          >
            {{ f.label }}
            <q-icon name="ph:x" size="14px" />
          </button>
          <button type="button" class="text-link" @click="resetFilters">
            {{ $t('catalogue.clear_all') }}
          </button>
        </div>

        <AppNotice v-if="cartError" tone="warning" class="catalogue__notice">
          {{ cartError }}
        </AppNotice>

        <!-- Chargement : squelettes à la forme des cartes -->
        <div v-if="store.loading" class="product-grid" aria-busy="true">
          <div v-for="n in 8" :key="n" class="skeleton-card">
            <q-skeleton square class="skeleton-card__media" />
            <q-skeleton type="text" width="40%" />
            <q-skeleton type="text" width="90%" />
            <q-skeleton type="text" width="55%" />
          </div>
        </div>

        <AppNotice v-else-if="store.error" tone="error">
          {{ store.error }}
          <template #action>
            <q-btn flat :label="$t('common.retry')" @click="store.search()" />
          </template>
        </AppNotice>

        <div v-else-if="store.items.length === 0" class="catalogue__empty">
          <q-icon name="ph:magnifying-glass" size="40px" class="text-subtle" />
          <h2>{{ $t('catalogue.no_match') }}</h2>
          <p>{{ $t('catalogue.no_match_hint') }}</p>
          <q-btn
            v-if="activeFilters.length > 0"
            outline
            color="primary"
            :label="$t('catalogue.clear_all')"
            @click="resetFilters"
          />
        </div>

        <div v-else class="product-grid">
          <ProductCard
            v-for="product in store.items"
            :key="product.id"
            :product="product"
            @add-to-cart="onAddToCart"
          />
        </div>

        <nav
          v-if="store.totalPages > 1"
          class="catalogue__pagination"
          :aria-label="$t('catalogue.pagination')"
        >
          <span class="font-mono text-subtle">{{
            $t('catalogue.page_of', { page: currentPage, total: store.totalPages })
          }}</span>
          <q-pagination
            v-model="currentPage"
            :max="store.totalPages"
            :max-pages="5"
            boundary-numbers
            direction-links
            flat
            color="grey-7"
            active-design="unelevated"
            active-color="primary"
            active-text-color="white"
            class="font-mono"
            @update:model-value="onPageChange"
          />
        </nav>
      </section>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useMeta } from 'quasar';
import { useI18n } from 'vue-i18n';
import { intlLocale } from '@app/utils';
import { useShopModulesStore } from '@/stores/shopModules';
import { useRoute, useRouter, type LocationQuery } from 'vue-router';
import { useProductsStore } from '@/stores/products';
import { useCartStore } from '@/stores/cart';
import { useCurrencyStore } from '@/stores/currency';
import { useUiStore } from '@/stores/ui';
import AppNotice from '@app/ui/AppNotice.vue';
import ProductCard from '@/components/ProductCard.vue';
import type { components } from '@app/api-types';

type ProductPublic = components['schemas']['ProductPublic'];
type SpecFacet = components['schemas']['SpecFacet'];

/** Fabricants affichés avant « Voir N autres ». */
const MANUFACTURERS_SHOWN = 6;

const store = useProductsStore();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();
const uiStore = useUiStore();
const { t } = useI18n();
const shopModules = useShopModulesStore();
const route = useRoute();
const router = useRouter();

useMeta(() => ({
  title: t('catalogue.meta_title', { shop: shopModules.config.shop_name || 'Natimai' }),
  meta: {
    description: {
      name: 'description',
      content: t('catalogue.meta_description'),
    },
  },
}));

const searchQuery = ref<string>('');
const selectedManufacturer = ref<string | null>(null);
const selectedCategory = ref<string | null>(null);
// null = new and refurbished together.
const selectedCondition = ref<'new' | 'refurbished' | null>(null);
// Counts of the current results (facets); null on « all » options.
const conditionOptions = computed(() => {
  const counts = store.facets?.conditions ?? {};
  return [
    { label: t('catalogue.new_and_refurbished'), value: null, count: null },
    { label: t('catalogue.new'), value: 'new' as const, count: counts['new'] ?? null },
    {
      label: t('catalogue.refurbished'),
      value: 'refurbished' as const,
      count: counts['refurbished'] ?? null,
    },
  ];
});
// Where the stock is: our warehouse (fast) or the supplier (longer delivery).
type StockLocation = 'local' | 'supplier';
const selectedStock = ref<StockLocation | null>(null);
const STOCK_LABELS = computed<Record<StockLocation, string>>(() => ({
  local: t('catalogue.stock_local'),
  supplier: t('catalogue.stock_supplier'),
}));
const stockOptions = computed(() => {
  const counts = store.facets?.stock ?? {};
  return [
    { label: t('catalogue.all_items'), value: null, count: null },
    { label: STOCK_LABELS.value.local, value: 'local' as const, count: counts['local'] ?? null },
    {
      label: STOCK_LABELS.value.supplier,
      value: 'supplier' as const,
      count: counts['supplier'] ?? null,
    },
  ];
});
// Spec filters: enum key → selected value_text[]; numeric key → minimum value.
const enumSelections = ref<Record<string, string[]>>({});
const numericMin = ref<Record<string, number | null>>({});
const priceMin = ref<number | ''>('');
const priceMax = ref<number | ''>('');
const cartError = ref<string | null>(null);
const filtersOpen = ref(false);
const showAllManufacturers = ref(false);

const categoryOptions = computed(() =>
  store.categories.map((c) => ({ label: c.title ?? c.name, value: c.id })),
);

const pageTitle = computed(() => {
  if (store.filters.q) return t('catalogue.results_for', { q: store.filters.q });
  const cat = categoryOptions.value.find((c) => c.value === selectedCategory.value);
  return cat?.label ?? t('catalogue.title');
});

const resultLabel = computed(() =>
  t(
    'catalogue.results',
    { n: new Intl.NumberFormat(intlLocale()).format(store.count) },
    store.count,
  ),
);

const manufacturerOptions = computed(() => {
  const mfrs = store.facets?.manufacturers ?? {};
  return Object.entries(mfrs)
    .sort((a, b) => b[1] - a[1])
    .map(([value, count]) => ({ value, count }));
});

const visibleManufacturers = computed(() => {
  const all = manufacturerOptions.value;
  if (showAllManufacturers.value || all.length <= MANUFACTURERS_SHOWN + 1) return all;
  const shown = all.slice(0, MANUFACTURERS_SHOWN);
  // Le fabricant choisi reste visible même s'il est au-delà de la coupure.
  const selected = all.find((o) => o.value === selectedManufacturer.value);
  if (selected && !shown.includes(selected)) shown.push(selected);
  return shown;
});

const hiddenManufacturerCount = computed(
  () => manufacturerOptions.value.length - visibleManufacturers.value.length,
);

function numericOptions(facet: SpecFacet): { label: string; value: number }[] {
  const seen = new Set<number>();
  const opts: { label: string; value: number }[] = [];
  for (const v of facet.values ?? []) {
    if (v.value_numeric == null) continue;
    const num = Number.parseFloat(v.value_numeric);
    if (!Number.isFinite(num) || seen.has(num)) continue;
    seen.add(num);
    opts.push({
      label: t('catalogue.and_more', {
        value: `${num}${facet.unit ? ' ' + facet.unit : ''}`,
        n: v.count,
      }),
      value: num,
    });
  }
  return opts.sort((a, b) => a.value - b.value);
}

/** Build the `specs` search payload: enum → key:[values], numeric → key_min:value. */
function buildSpecs(): Record<string, unknown> {
  const specs: Record<string, unknown> = {};
  for (const [key, vals] of Object.entries(enumSelections.value)) {
    if (vals.length > 0) specs[key] = vals;
  }
  for (const [key, min] of Object.entries(numericMin.value)) {
    if (min != null) specs[`${key}_min`] = min;
  }
  return specs;
}

type ActiveFilter = { key: string; label: string; remove: () => void };

/** Filtres en cours, affichés en puces retirables au-dessus de la grille. */
const activeFilters = computed<ActiveFilter[]>(() => {
  const list: ActiveFilter[] = [];
  const q = store.filters.q;
  if (q) {
    list.push({
      key: 'q',
      label: `« ${q} »`,
      remove: () => {
        searchQuery.value = '';
        void store.applyFilters({ q: null }).then(syncQueryParams);
      },
    });
  }
  if (selectedStock.value) {
    list.push({
      key: 'stock',
      label: STOCK_LABELS.value[selectedStock.value],
      remove: () => void onStockChange(null),
    });
  }
  if (selectedCondition.value) {
    list.push({
      key: 'cond',
      label: selectedCondition.value === 'new' ? t('catalogue.new') : t('catalogue.refurbished'),
      remove: () => void onConditionChange(null),
    });
  }
  if (selectedManufacturer.value) {
    list.push({
      key: 'mfr',
      label: selectedManufacturer.value,
      remove: () => void onManufacturerChange(null),
    });
  }
  for (const facet of store.specFacets) {
    for (const value of enumSelections.value[facet.key] ?? []) {
      list.push({
        key: `enum-${facet.key}-${value}`,
        label: value,
        remove: () => onEnumToggle(facet.key, value, false),
      });
    }
    const min = numericMin.value[facet.key];
    if (min != null) {
      list.push({
        key: `num-${facet.key}`,
        label: t('catalogue.spec_and_more', {
          label: facet.label_fr,
          value: `${min}${facet.unit ? ' ' + facet.unit : ''}`,
        }),
        remove: () => onNumericChange(facet.key, null),
      });
    }
  }
  const { price_min: pMin, price_max: pMax } = store.filters;
  if (pMin != null || pMax != null) {
    const label =
      pMin != null && pMax != null
        ? t('catalogue.price_between', {
            min: currencyStore.format(pMin),
            max: currencyStore.format(pMax),
          })
        : pMin != null
          ? t('catalogue.price_from', { min: currencyStore.format(pMin) })
          : t('catalogue.price_to', { max: currencyStore.format(pMax ?? 0) });
    list.push({
      key: 'price',
      label,
      remove: () => {
        priceMin.value = '';
        priceMax.value = '';
        void onPriceChange();
      },
    });
  }
  return list;
});

const currentPage = computed({
  get: () => store.currentPage,
  set: (v) => {
    store.currentPage = v;
  },
});

async function onPageChange(page: number) {
  await store.setPage(page);
  window.scrollTo({ top: 0 });
}

async function onConditionChange(val: 'new' | 'refurbished' | null) {
  selectedCondition.value = val;
  await store.applyFilters({ condition: val });
  syncQueryParams();
}

async function onStockChange(val: StockLocation | null) {
  selectedStock.value = val;
  await store.applyFilters({ stock: val });
  syncQueryParams();
}

async function onManufacturerChange(val: string | null) {
  selectedManufacturer.value = val;
  await store.applyFilters({ manufacturer: val });
  syncQueryParams();
}

async function onCategoryChange(catId: string | null) {
  if (catId === selectedCategory.value) return;
  selectedCategory.value = catId;
  // Spec facets are per-category — reset any previous spec selection.
  enumSelections.value = {};
  numericMin.value = {};
  await store.loadSpecFacets(catId);
  await store.applyFilters({ category_id: catId, specs: {} });
  syncQueryParams();
}

function onSpecChange() {
  void store.applyFilters({ specs: buildSpecs() });
}

function onNumericSelect(key: string, event: Event) {
  const raw = (event.target as HTMLSelectElement).value;
  onNumericChange(key, raw === '' ? null : Number(raw));
}

function onNumericChange(key: string, value: number | null) {
  numericMin.value = { ...numericMin.value, [key]: value };
  onSpecChange();
}

function onEnumToggle(key: string, value: string, checked: boolean) {
  const current = enumSelections.value[key] ?? [];
  const next = checked ? [...current, value] : current.filter((v) => v !== value);
  enumSelections.value = { ...enumSelections.value, [key]: next };
  onSpecChange();
}

async function onPriceChange() {
  await store.applyFilters({
    price_min: priceMin.value === '' ? null : priceMin.value,
    price_max: priceMax.value === '' ? null : priceMax.value,
  });
}

async function resetFilters() {
  searchQuery.value = '';
  selectedManufacturer.value = null;
  selectedCategory.value = null;
  selectedCondition.value = null;
  selectedStock.value = null;
  enumSelections.value = {};
  numericMin.value = {};
  priceMin.value = '';
  priceMax.value = '';
  showAllManufacturers.value = false;
  await store.loadSpecFacets(null);
  await store.applyFilters({
    q: null,
    manufacturer: null,
    category_id: null,
    in_stock: null,
    stock: null,
    condition: null,
    price_min: null,
    price_max: null,
    specs: {},
  });
  void router.replace({ query: {} });
}

function stateQuery(): Record<string, string> {
  const query: Record<string, string> = {};
  if (searchQuery.value) query['q'] = searchQuery.value;
  if (selectedManufacturer.value) query['mfr'] = selectedManufacturer.value;
  if (selectedCategory.value) query['cat'] = selectedCategory.value;
  if (selectedCondition.value) query['cond'] = selectedCondition.value;
  if (selectedStock.value) query['stock'] = selectedStock.value;
  return query;
}

function syncQueryParams() {
  void router.replace({ query: stateQuery() });
}

async function onAddToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? t('catalogue.add_failed');
}

function initFromQuery(query: LocationQuery = route.query) {
  const q = query['q'];
  const mfr = query['mfr'];
  const cat = query['cat'];
  searchQuery.value = typeof q === 'string' ? q : '';
  selectedManufacturer.value = typeof mfr === 'string' ? mfr : null;
  selectedCategory.value = typeof cat === 'string' ? cat : null;
  const cond = query['cond'];
  selectedCondition.value = cond === 'new' || cond === 'refurbished' ? cond : null;
  const stock = query['stock'];
  selectedStock.value = stock === 'local' || stock === 'supplier' ? stock : null;
}

async function loadCatalogueData() {
  initFromQuery();
  await store.loadCategories();
  await store.loadSpecFacets(selectedCategory.value);
  await store.applyFilters({
    q: searchQuery.value || null,
    manufacturer: selectedManufacturer.value,
    category_id: selectedCategory.value,
    condition: selectedCondition.value,
    stock: selectedStock.value,
    specs: buildSpecs(),
  });
}

// La recherche de l'en-tête (ou un lien) change l'URL : on recharge alors le
// catalogue depuis l'URL, en ignorant les URL que la page a elle-même écrites.
watch(
  () => route.query,
  (query) => {
    if (route.name !== 'catalogue') return;
    const current = stateQuery();
    const keys = ['q', 'mfr', 'cat', 'cond', 'stock'];
    const same =
      keys.every((k) => (query[k] ?? undefined) === current[k]) &&
      Object.keys(query).every((k) => keys.includes(k));
    if (same) return;
    const categoryChanged = (query['cat'] ?? null) !== selectedCategory.value;
    if (categoryChanged) {
      enumSelections.value = {};
      numericMin.value = {};
    }
    void loadCatalogueData();
  },
);

onServerPrefetch(loadCatalogueData);

onMounted(async () => {
  await loadCatalogueData();
});
</script>

<style scoped lang="scss">
.catalogue {
  padding-top: 20px;
  padding-bottom: 72px;
}

.catalogue__cats {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
  margin: 0 -40px;
  padding: 0 40px 4px;

  &::-webkit-scrollbar {
    display: none;
  }

  @media (max-width: 767px) {
    margin: 0 -16px;
    padding: 0 16px 4px;
  }
}

.chip {
  flex-shrink: 0;
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--n-line);
  border-radius: 999px;
  background: transparent;
  color: var(--n-ink-2);
  font: inherit;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);

  &:hover {
    border-color: var(--n-line-2);
    color: var(--n-ink);
  }

  &:active {
    transform: scale(0.98);
  }

  &--active,
  &--active:hover {
    border-color: var(--n-ink);
    background: var(--n-ink);
    color: var(--n-on-ink);
  }
}

.catalogue__layout {
  margin-top: 36px;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 48px;
  align-items: start;

  @media (max-width: 1023px) {
    margin-top: 24px;
    grid-template-columns: minmax(0, 1fr);
  }
}

// Filtres
.filters__fieldset {
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filters__body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.filters__group {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;

  & + & {
    padding-top: 24px;
    border-top: 1px solid var(--n-line);
  }
}

.filters__legend {
  padding: 0;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-ink);
}

.filters__option {
  min-height: 28px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  cursor: pointer;

  input {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    margin: 0;
    accent-color: var(--n-accent);
    cursor: pointer;
  }
}

.filters__option-label {
  flex-grow: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filters__count {
  font-size: 12px;
  color: var(--n-ink-3);
}

.filters__more {
  align-self: flex-start;
  margin-top: 4px;
}

.filters__price {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.filters__apply {
  margin-top: 4px;
  min-height: 40px;
}

.filters__reset {
  align-self: flex-start;
}

.filters__sheet-head,
.filters__sheet-foot {
  display: none;
}

@media (max-width: 1023px) {
  .filters {
    display: none;
  }

  .filters--open {
    position: fixed;
    inset: 0;
    z-index: 3000; // au-dessus de l'en-tête Quasar (2000)
    display: flex;
    flex-direction: column;
    background: var(--n-surface);
  }

  .filters__sheet-head {
    flex-shrink: 0;
    height: 56px;
    padding: 0 8px 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--n-line);
  }

  .filters__sheet-title {
    font-size: 16px;
    font-weight: 600;
  }

  .filters__body {
    flex-grow: 1;
    overflow-y: auto;
    padding: 24px 16px;
  }

  .filters__sheet-foot {
    flex-shrink: 0;
    display: block;
    padding: 12px 16px 20px;
    border-top: 1px solid var(--n-line);

    .q-btn {
      min-height: 48px;
    }
  }
}

// Champs
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.field__label {
  font-size: 12px;
  color: var(--n-ink-2);
}

.field-input {
  width: 100%;
  height: 40px;
  padding: 0 10px;
  border: 1px solid var(--n-line-2);
  border-radius: 8px;
  background: var(--n-surface);
  color: var(--n-ink);
  font: inherit;
  font-size: 14px;
  outline: 0;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;

  &:focus {
    border-color: var(--n-accent);
    box-shadow: 0 0 0 3px var(--n-accent-soft);
  }

  @media (max-width: 1023px) {
    height: 44px;
    font-size: 16px;
  }
}

// Résultats
.catalogue__results {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

.catalogue__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.catalogue__heading {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 14px;
  min-width: 0;
}

.catalogue__count {
  font-size: 13px;
  color: var(--n-ink-3);
}

.catalogue__active {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.active-filter {
  height: 32px;
  padding: 0 10px 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  border-radius: 999px;
  background: var(--n-accent-soft);
  color: var(--n-accent);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);

  &:active {
    transform: scale(0.97);
  }
}

.text-link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--n-ink-2);
  font: inherit;
  font-size: 13px;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;

  &:hover {
    color: var(--n-accent);
  }
}

.catalogue__empty {
  padding: 72px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;

  h2 {
    margin: 8px 0 0;
    font-size: 18px;
    font-weight: 600;
    line-height: 1.3;
  }

  p {
    margin: 0 0 12px;
    color: var(--n-ink-2);
  }
}

.catalogue__pagination {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid var(--n-line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;

  @media (max-width: 767px) {
    flex-direction: column;
  }
}
</style>
