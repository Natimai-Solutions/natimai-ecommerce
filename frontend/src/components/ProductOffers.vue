<template>
  <section v-if="others.length > 0" class="offers" aria-labelledby="offers-title">
    <h2 id="offers-title" class="offers__title">
      {{ others.length === 1 ? 'Autre offre pour cet article' : 'Autres offres pour cet article' }}
    </h2>
    <router-link
      v-for="offer in others"
      :key="offer.product_id"
      :to="getProductRouteByIdAndName(offer.product_id, offer.name)"
      class="offers__row"
      @click="emit('navigate')"
    >
      <span class="offers__who">
        <span class="offers__name">{{ offer.supplier_label ?? offer.name }}</span>
        <span class="offers__detail">{{ detailOf(offer) }}</span>
      </span>
      <span class="offers__price-col">
        <span class="offers__price font-mono">{{ priceOf(offer) }}</span>
        <span v-if="offer.product_id === cheapestId" class="offers__best">Meilleur prix</span>
      </span>
    </router-link>
    <p v-if="currentIsCheapest" class="offers__note">
      <q-icon name="ph:check-circle" size="16px" />Cette offre est la moins chère.
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  sellableQuantity,
  type ProductOfferPublic,
  type ProductOffersResponse,
} from '@/api/products';
import { useCurrencyStore } from '@/stores/currency';
import { getProductRouteByIdAndName } from '@/utils/productRoute';

const props = defineProps<{ offers: ProductOffersResponse | null }>();
const emit = defineEmits<{ navigate: [] }>();

const currencyStore = useCurrencyStore();

const others = computed(() => (props.offers?.offers ?? []).filter((o) => !o.is_current));
const cheapestId = computed(() => props.offers?.cheapest_product_id ?? null);
const currentIsCheapest = computed(() => {
  const current = props.offers?.offers.find((o) => o.is_current);
  return !!current && current.product_id === cheapestId.value && others.value.length > 0;
});

function priceOf(offer: ProductOfferPublic): string {
  const price = parseFloat(offer.sale_price);
  return price > 0 ? currencyStore.format(price) : 'Prix sur devis';
}

/** « En stock chez nous (2) », « Chez le fournisseur (5), import »… */
function detailOf(offer: ProductOfferPublic): string {
  const local = Math.max(0, Math.round(parseFloat(offer.local_quantity ?? '0') || 0));
  const supplier = Math.max(0, sellableQuantity(offer) - local);
  const origin = offer.is_domestic ? 'fournisseur local' : 'import';
  if (local > 0) return `En stock chez nous (${local})`;
  if (supplier > 0) return `En stock chez le fournisseur (${supplier}), ${origin}`;
  return `Sur commande, ${origin}`;
}
</script>

<style scoped lang="scss">
.offers {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.offers__title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
}

.offers__row {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  color: var(--n-ink);
  text-decoration: none;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;

  &:hover {
    border-color: var(--n-line-2);
    background: var(--n-bg);
  }
}

.offers__who,
.offers__price-col {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.offers__price-col {
  flex-shrink: 0;
  align-items: flex-end;
}

.offers__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.offers__detail {
  font-size: 13px;
  color: var(--n-ink-3);
}

.offers__price {
  font-size: 15px;
  font-weight: 600;
}

.offers__best {
  font-size: 12px;
  font-weight: 500;
  color: var(--n-accent);
}

.offers__note {
  margin: 4px 0 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--n-ink-2);
}
</style>
