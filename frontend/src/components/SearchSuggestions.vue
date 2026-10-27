<template>
  <div
    v-if="open && query.trim().length >= MIN_LENGTH && (loading || suggestions.length > 0)"
    class="search-suggest"
    role="listbox"
    :aria-label="$t('layout.suggest_label')"
    data-testid="search-suggestions"
    @mousedown.prevent
  >
    <p v-if="approximate" class="search-suggest__note">{{ $t('layout.suggest_approximate') }}</p>
    <div v-if="loading && suggestions.length === 0" class="search-suggest__row" aria-busy="true">
      <q-skeleton type="text" width="70%" />
    </div>
    <router-link
      v-for="product in suggestions"
      :key="product.id"
      :to="getProductRoute(product)"
      class="search-suggest__row"
      role="option"
      @click="emit('picked')"
    >
      <span class="search-suggest__media">
        <ProductImage :src="product.image_url ?? product.supplier_image_url" :alt="product.name" />
      </span>
      <span class="search-suggest__text">
        <span class="search-suggest__name">{{ product.name }}</span>
        <span v-if="product.manufacturer" class="search-suggest__brand">
          {{ product.manufacturer }}
        </span>
      </span>
      <span class="search-suggest__price font-mono">{{ money(product.base_price) }}</span>
    </router-link>
    <button type="button" class="search-suggest__all" @click="emit('submit')">
      {{ $t('layout.suggest_all', { q: query.trim() }) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';
import type { components } from '@app/api-types';

import ProductImage from '@/components/ProductImage.vue';
import { suggestProducts } from '@/api/products';
import { useCurrencyStore } from '@/stores/currency';
import { getProductRoute } from '@/utils/productRoute';

type ProductPublic = components['schemas']['ProductPublic'];

/**
 * A few products under the search field while the visitor types (same
 * matching as the catalogue: accents and typos included). Typing goes on as
 * usual: Enter still opens the full results.
 */
const props = defineProps<{ query: string; open: boolean }>();
const emit = defineEmits<{ picked: []; submit: [] }>();

const MIN_LENGTH = 2;
const DEBOUNCE_MS = 200;

const currencyStore = useCurrencyStore();
const suggestions = ref<ProductPublic[]>([]);
const approximate = ref(false);
const loading = ref(false);
let timer: ReturnType<typeof setTimeout> | null = null;
// Answers can arrive out of order: only the last request's is shown.
let sequence = 0;

function money(raw: string | number | null | undefined): string {
  const value = Number(raw ?? 0);
  return currencyStore.format(Number.isFinite(value) ? value : 0);
}

async function fetchSuggestions(q: string) {
  const ticket = ++sequence;
  loading.value = true;
  try {
    const result = await suggestProducts(q);
    if (ticket !== sequence) return;
    suggestions.value = result.data ?? [];
    approximate.value = result.approximate ?? false;
  } catch {
    if (ticket === sequence) suggestions.value = [];
  } finally {
    if (ticket === sequence) loading.value = false;
  }
}

// Only the open field asks the server (the header has a desktop and a mobile one).
watch(
  () => [props.query, props.open] as const,
  ([raw, open]) => {
    if (timer) clearTimeout(timer);
    const q = raw.trim();
    if (!open || q.length < MIN_LENGTH) {
      sequence++;
      suggestions.value = [];
      approximate.value = false;
      loading.value = false;
      return;
    }
    timer = setTimeout(() => void fetchSuggestions(q), DEBOUNCE_MS);
  },
);

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
});
</script>

<style scoped lang="scss">
.search-suggest {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 3000;
  padding: 6px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-bg);
  box-shadow: var(--n-shadow);
}

.search-suggest__note {
  margin: 4px 8px 6px;
  font-size: 12px;
  color: var(--n-ink-3);
}

.search-suggest__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  color: var(--n-ink);
  text-decoration: none;

  &:hover,
  &:focus-visible {
    background: var(--n-tile-hover);
    outline: none;
  }
}

.search-suggest__media {
  flex: 0 0 36px;
  width: 36px;
}

.search-suggest__text {
  display: grid;
  flex-grow: 1;
  min-width: 0;
}

.search-suggest__name {
  overflow: hidden;
  font-size: 14px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.search-suggest__brand {
  font-size: 12px;
  color: var(--n-ink-3);
}

.search-suggest__price {
  font-size: 13px;
  white-space: nowrap;
}

.search-suggest__all {
  width: 100%;
  margin-top: 4px;
  padding: 8px;
  border: 0;
  border-top: 1px solid var(--n-line);
  background: transparent;
  color: var(--n-accent);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
</style>
