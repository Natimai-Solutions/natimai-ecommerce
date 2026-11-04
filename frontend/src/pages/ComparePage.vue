<template>
  <q-page class="compare page-container">
    <div class="compare__head">
      <h1 class="page-title">{{ $t('compare.title') }}</h1>
      <span v-if="products.length" class="font-mono text-subtle">
        {{ $t('compare.count', { n: products.length, max: COMPARE_MAX }) }}
      </span>
      <q-btn
        v-if="products.length"
        flat
        no-caps
        dense
        :label="$t('compare.clear')"
        class="compare__clear"
        @click="clearAll"
      />
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">
      {{ error }}
      <template #action><q-btn flat :label="$t('common.retry')" @click="load" /></template>
    </AppNotice>
    <AppNotice v-if="cartError" tone="warning" dense class="q-mb-md">{{ cartError }}</AppNotice>

    <div v-if="loading && !products.length" class="compare__loading" aria-busy="true">
      <q-skeleton type="rect" height="320px" />
    </div>

    <div v-else-if="!products.length" class="compare__empty" data-testid="compare-empty">
      <q-icon name="ph:scales" size="40px" class="compare__empty-icon" />
      <h2 class="compare__empty-title">{{ $t('compare.empty_title') }}</h2>
      <p class="text-subtle">{{ $t('compare.empty_text', { max: COMPARE_MAX }) }}</p>
      <q-btn
        unelevated
        no-caps
        color="primary"
        :label="$t('compare.browse')"
        :to="{ name: 'catalogue' }"
      />
    </div>

    <template v-else>
      <label v-if="rows.length" class="compare__filter">
        <q-toggle v-model="differencesOnly" dense :label="$t('compare.differences')" />
      </label>

      <div class="compare__scroll">
        <table class="compare__table" data-testid="compare-table">
          <thead>
            <tr>
              <th scope="col" class="compare__corner"></th>
              <th
                v-for="product in products"
                :key="product.id"
                scope="col"
                class="compare__product"
              >
                <router-link :to="getProductRoute(product)" class="compare__media" tabindex="-1">
                  <ProductImage
                    :src="product.image_url ?? product.supplier_image_url"
                    :alt="product.name"
                  />
                </router-link>
                <router-link :to="getProductRoute(product)" class="compare__name">
                  {{ product.name }}
                </router-link>
                <span class="compare__brand">{{ product.manufacturer ?? '' }}</span>
                <button
                  type="button"
                  class="compare__remove text-link"
                  :aria-label="$t('compare.remove', { name: product.name })"
                  @click="remove(product.id)"
                >
                  {{ $t('compare.remove_short') }}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">{{ $t('compare.price') }}</th>
              <td v-for="product in products" :key="product.id">
                <span v-if="isQuote(product)">{{ $t('card.on_quote') }}</span>
                <span v-else class="font-mono compare__price">{{ price(product) }}</span>
              </td>
            </tr>
            <tr>
              <th scope="row">{{ $t('compare.availability') }}</th>
              <td v-for="product in products" :key="product.id">
                {{ availabilityOf(product).label }}
              </td>
            </tr>
            <tr>
              <th scope="row">{{ $t('compare.condition') }}</th>
              <td v-for="product in products" :key="product.id">
                {{ conditionLabel(product, tr) }}
              </td>
            </tr>
            <tr v-for="row in visibleRows" :key="row.key" :data-spec="row.key">
              <th scope="row">{{ row.label }}</th>
              <td v-for="product in products" :key="product.id">
                <span v-if="valueOf(row, product.id)">{{ valueOf(row, product.id) }}</span>
                <span v-else class="text-subtle">—</span>
              </td>
            </tr>
            <tr>
              <th scope="row"></th>
              <td v-for="product in products" :key="product.id">
                <q-btn
                  v-if="product.has_variants"
                  outline
                  no-caps
                  color="primary"
                  :label="$t('compare.choose')"
                  :to="getProductRoute(product)"
                />
                <q-btn
                  v-else
                  unelevated
                  no-caps
                  color="primary"
                  :label="$t('compare.add_to_cart')"
                  :disable="!availabilityOf(product).orderable"
                  :loading="cartStore.mutating"
                  @click="addToCart(product)"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="rows.length && differencesOnly && !visibleRows.length" class="text-subtle">
        {{ $t('compare.no_differences') }}
      </p>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { components } from '@app/api-types';
import AppNotice from '@app/ui/AppNotice.vue';
import ProductImage from '@/components/ProductImage.vue';
import { compareProducts, type CompareRow } from '@/api/products';
import { usePageMeta } from '@/composables/usePageMeta';
import { useTranslate } from '@/composables/useTranslate';
import { useCartStore } from '@/stores/cart';
import { COMPARE_MAX, useCompareStore } from '@/stores/compare';
import { useCurrencyStore } from '@/stores/currency';
import { useUiStore } from '@/stores/ui';
import { conditionLabel, productAvailability } from '@/utils/availability';
import { apiErrorMessage } from '@/utils/errors';
import { getProductRoute } from '@/utils/productRoute';

type ProductPublic = components['schemas']['ProductPublic'];

/**
 * Side-by-side comparison of the shortlist (R8 / confort): the products as
 * the catalogue shows them, then one row per spec at least one of them has.
 * The shortlist lives in the browser (stores/compare.ts); the table comes
 * from the API so that the wording matches the product pages.
 */
const { t } = useI18n();
const tr = useTranslate();
const compareStore = useCompareStore();
const cartStore = useCartStore();
const uiStore = useUiStore();
const currencyStore = useCurrencyStore();

usePageMeta(() => ({ title: t('compare.meta_title'), noindex: true }));

const products = ref<ProductPublic[]>([]);
const rows = ref<CompareRow[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const cartError = ref<string | null>(null);
const differencesOnly = ref(false);

const visibleRows = computed(() =>
  differencesOnly.value
    ? rows.value.filter((row) => new Set(Object.values(row.values ?? {})).size > 1)
    : rows.value,
);

function valueOf(row: CompareRow, productId: string): string | null {
  return row.values?.[productId] ?? null;
}
function isQuote(product: ProductPublic): boolean {
  return parseFloat(product.base_price) === 0;
}
function price(product: ProductPublic): string {
  return currencyStore.format(parseFloat(product.base_price));
}
function availabilityOf(product: ProductPublic) {
  return productAvailability(product, tr);
}

async function load() {
  compareStore.load();
  if (!compareStore.ids.length) {
    products.value = [];
    rows.value = [];
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const result = await compareProducts(compareStore.ids);
    products.value = result.products;
    rows.value = result.rows;
    // Products gone from the catalogue leave the shortlist too.
    const kept = new Set(result.products.map((p) => p.id));
    compareStore.ids.filter((id) => !kept.has(id)).forEach((id) => compareStore.remove(id));
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('compare.load_failed');
  } finally {
    loading.value = false;
  }
}

function remove(productId: string) {
  compareStore.remove(productId);
  products.value = products.value.filter((p) => p.id !== productId);
}

function clearAll() {
  compareStore.clear();
  products.value = [];
  rows.value = [];
}

async function addToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? t('catalogue.add_failed');
}

watch(
  () => compareStore.ids.length,
  (next, previous) => {
    // Added from another tab or the bar: refresh; removals are handled locally.
    if (next > previous) void load();
  },
);

onMounted(load);
</script>

<style scoped lang="scss">
.compare {
  padding-top: 32px;
  padding-bottom: 96px;
}

.compare__head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 20px;
}

.compare__clear {
  margin-left: auto;
  color: var(--n-ink-3);
}

.compare__filter {
  display: inline-flex;
  margin-bottom: 12px;
}

.compare__empty {
  padding: 64px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.compare__empty-icon {
  color: var(--n-ink-3);
}

.compare__empty-title {
  margin: 0;
  font-size: 20px;
}

.compare__scroll {
  overflow-x: auto;
  margin-right: -16px;
  padding-right: 16px;
}

.compare__table {
  width: 100%;
  min-width: 560px;
  border-collapse: collapse;
  table-layout: fixed;

  th,
  td {
    padding: 12px 10px;
    border-bottom: 1px solid var(--n-line);
    vertical-align: top;
    text-align: left;
    font-size: 14px;
  }

  thead th {
    border-bottom: 1px solid var(--n-line-2);
    vertical-align: bottom;
  }

  tbody th {
    width: 180px;
    font-weight: 500;
    color: var(--n-ink-2);
  }
}

.compare__corner {
  width: 180px;
}

.compare__product {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.compare__media {
  display: block;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: var(--n-radius);
  background: var(--n-tile);
}

.compare__name {
  color: var(--n-ink);
  font-weight: 600;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}

.compare__brand {
  font-size: 12px;
  color: var(--n-ink-3);
}

.compare__remove {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  font-size: 13px;
  cursor: pointer;
}

.compare__price {
  font-weight: 600;
}

@media (max-width: 599px) {
  .compare__table tbody th,
  .compare__corner {
    width: 120px;
  }
}
</style>
