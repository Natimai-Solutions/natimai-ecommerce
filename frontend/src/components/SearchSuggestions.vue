<template>
  <div
    v-if="expanded"
    :id="listboxId"
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
      v-for="(product, index) in suggestions"
      :id="optionId(index)"
      :key="product.id"
      :to="getProductRoute(product)"
      class="search-suggest__row"
      :class="{ 'search-suggest__row--active': index === active }"
      role="option"
      :aria-selected="index === active"
      tabindex="-1"
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
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
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
const props = defineProps<{ query: string; open: boolean; listboxId: string }>();
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

/*
 * Keyboard (audit 2026-11, U7): the search field is a combobox. Arrows move
 * through the suggestions (announced via `aria-activedescendant`), Enter
 * opens the highlighted one, Escape stays the field's own (closes).
 */
const router = useRouter();
const active = ref(-1);
const expanded = computed(
  () =>
    props.open &&
    props.query.trim().length >= MIN_LENGTH &&
    (loading.value || suggestions.value.length > 0),
);
const activeId = computed(() => (active.value >= 0 ? optionId(active.value) : undefined));

function optionId(index: number): string {
  return `${props.listboxId}-option-${index}`;
}

watch(suggestions, () => {
  active.value = -1;
});

/** Handles the field's key; true when it consumed it. */
function handleKey(event: KeyboardEvent): boolean {
  const count = suggestions.value.length;
  if (!expanded.value || count === 0) return false;
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const step = event.key === 'ArrowDown' ? 1 : -1;
    active.value = (active.value + step + count + 1) % (count + 1);
    if (active.value === count) active.value = -1; // back to the typed text
    return true;
  }
  if (event.key === 'Enter' && active.value >= 0) {
    event.preventDefault();
    const product = suggestions.value[active.value];
    if (product) {
      emit('picked');
      void router.push(getProductRoute(product));
    }
    return true;
  }
  return false;
}

defineExpose({ handleKey, expanded, activeId });
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
  border-radius: var(--n-radius);
  background: var(--n-bg);
  box-shadow: var(--n-shadow);
}

.search-suggest__row--active {
  background: var(--n-surface);
  outline: 2px solid var(--n-accent);
  outline-offset: -2px;
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
