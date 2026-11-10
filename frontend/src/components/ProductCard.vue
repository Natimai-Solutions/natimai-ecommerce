<template>
  <article class="product-card" data-testid="product-card">
    <router-link :to="productRoute" class="product-card__media" tabindex="-1" aria-hidden="true">
      <ProductImage :src="imageUrl" :alt="product.name" />
    </router-link>

    <div class="product-card__info">
      <span class="product-card__brand">
        {{ brand }}<span v-if="brand" aria-hidden="true"> · </span
        ><span
          class="product-card__condition"
          :class="{ 'product-card__condition--refurbished': refurbished }"
          data-testid="product-condition"
          >{{ conditionLabel(product, tr) }}</span
        >
      </span>
      <router-link :to="productRoute" class="product-card__name">{{ product.name }}</router-link>
      <span v-if="product.vendor_part_number" class="product-card__ref font-mono">
        {{ product.vendor_part_number }}
      </span>
    </div>

    <div class="product-card__buy">
      <div class="product-card__meta">
        <span v-if="isQuote" class="product-card__price">{{ $t('card.on_quote') }}</span>
        <span v-else class="product-card__price">
          <span v-if="product.has_variants" class="product-card__from">{{ $t('card.from') }}</span>
          <span class="font-mono" :class="{ 'product-card__promo-price': regularPrice }">{{
            displayPrice
          }}</span>
          <span class="product-card__tax">{{ $t('card.incl_tax') }}</span>
        </span>
        <span v-if="regularPrice" class="product-card__promo" data-testid="product-card-promo">
          <s class="font-mono">{{ regularPrice }}</s>
          <span class="product-card__promo-badge">{{ promoBadge }}</span>
        </span>

        <span
          class="product-card__stock"
          :class="{
            'product-card__stock--order': availability.preorder || !availability.orderable,
          }"
          data-testid="product-card-stock"
          :data-source="availability.source"
        >
          <span
            class="stock-dot"
            :class="{
              'stock-dot--order': availability.preorder || !availability.orderable,
              'stock-dot--supplier': availability.source === 'supplier',
            }"
            aria-hidden="true"
          />{{ availability.label }}
        </span>
        <span v-if="availability.note" class="product-card__offers">
          {{ availability.note }}
        </span>
        <span v-if="showDeparture" class="product-card__offers">
          {{ nextDelivery }}
        </span>

        <span v-if="variantsCount > 1" class="product-card__offers">
          {{ $t('card.variants', { n: variantsCount }) }}
        </span>

        <span v-if="offersCount > 1" class="product-card__offers">
          {{ $t('card.offers', { n: offersCount }) }}
        </span>
      </div>

      <button
        type="button"
        class="product-card__compare"
        :class="{ 'product-card__compare--on': inCompare }"
        :aria-pressed="inCompare"
        :aria-label="
          inCompare
            ? $t('compare.remove', { name: product.name })
            : $t('compare.add', { name: product.name })
        "
        :title="inCompare ? $t('compare.remove_short') : $t('compare.add_short')"
        data-testid="product-compare"
        @click="toggleCompare"
      >
        <q-icon name="ph:scales" size="18px" />
      </button>
      <router-link
        v-if="product.has_variants"
        :to="productRoute"
        class="product-card__add"
        data-testid="product-choose-variant"
        :aria-label="$t('card.choose_variant', { name: product.name })"
      >
        <q-icon name="ph:arrow-right" size="20px" />
      </router-link>
      <button
        v-else
        type="button"
        class="product-card__add"
        data-testid="product-add-to-cart"
        :disabled="!availability.orderable"
        :aria-label="
          availability.orderable
            ? $t('card.add', { name: product.name })
            : $t('card.unavailable_now')
        "
        @click="emit('add-to-cart', product)"
      >
        <q-icon name="ph:plus" size="20px" />
      </button>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { components } from '@app/api-types';
import ProductImage from '@/components/ProductImage.vue';
import { getProductRoute } from '@/utils/productRoute';
import { useCompareStore } from '@/stores/compare';
import { useCurrencyStore } from '@/stores/currency';
import { useDepartureLabels } from '@/composables/useDepartureLabels';
import { useTranslate } from '@/composables/useTranslate';
import { conditionLabel, isRefurbished, productAvailability } from '@/utils/availability';

// `offers_count` is served by the backend (search grouping of the same item
// sold by several suppliers) but the generated schema may lag — read it loosely.
type ProductPublic = components['schemas']['ProductPublic'] & { offers_count?: number };

const props = defineProps<{ product: ProductPublic }>();
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic]; 'compare-full': [] }>();

// Comparison shortlist (R8 / confort): a toggle on every card.
const compareStore = useCompareStore();
const inCompare = computed(() => compareStore.has(props.product.id));
function toggleCompare() {
  if (!compareStore.toggle(props.product.id)) emit('compare-full');
}

const currencyStore = useCurrencyStore();

const offersCount = computed(() => props.product.offers_count ?? 1);
const productRoute = computed(() => getProductRoute(props.product));
const imageUrl = computed(() => props.product.image_url ?? props.product.supplier_image_url);
const brand = computed(() => props.product.manufacturer ?? props.product.supplier_name ?? '');

const tr = useTranslate();
const { nextDelivery } = useDepartureLabels();
const availability = computed(() => productAvailability(props.product, tr));
const refurbished = computed(() => isRefurbished(props.product));
// Our warehouse stock does not wait for the grouped departure's date.
const showDeparture = computed(
  () =>
    !!nextDelivery.value && availability.value.orderable && availability.value.source !== 'local',
);
const variantsCount = computed(() => props.product.variants_count ?? 0);

const isQuote = computed(() => parseFloat(props.product.base_price) === 0);
// A parent is listed at its cheapest variant, prefixed « À partir de ».
const displayPrice = computed(() => currencyStore.format(parseFloat(props.product.base_price)));
// Promotion : le prix habituel du client, barré, et la remise obtenue.
const regularPrice = computed(() => {
  const regular = props.product.regular_price;
  return regular ? currencyStore.format(parseFloat(regular)) : null;
});
const promoBadge = computed(() => {
  const regular = parseFloat(props.product.regular_price ?? '0');
  const price = parseFloat(props.product.base_price);
  if (!(regular > 0) || !(price < regular)) return tr('card.promo');
  return `−${Math.round((1 - price / regular) * 100)} %`;
});
</script>

<style scoped lang="scss">
.product-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.product-card__media {
  display: block;
  text-decoration: none;

  &:hover :deep(.product-image) {
    background: var(--n-photo-hover);
  }

  &:hover :deep(.product-image__img) {
    transform: scale(1.04);
  }
}

.product-card__info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.product-card__brand {
  min-height: 1.4em;
  font-size: 13px;
  color: var(--n-ink-2);
}

.product-card__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.7em;
  font-size: 15px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--n-ink);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.product-card__ref {
  font-size: 12px;
  color: var(--n-ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.product-card__buy {
  margin-top: auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.product-card__meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.product-card__promo {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--n-ink-2);
}

.product-card__promo-badge {
  padding: 1px 6px;
  border-radius: var(--n-radius-sm);
  font-weight: 600;
  color: var(--n-on-accent);
  background: var(--n-accent);
}

.product-card__promo-price {
  color: var(--n-accent);
}

.product-card__tax {
  margin-left: 4px;
  font-size: 11px;
  font-weight: 500;
  color: var(--n-ink-2);
}

.product-card__price {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--n-ink);
}

.product-card__from {
  display: block;
  font-size: 12px;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--n-ink-3);
}

.product-card__condition {
  color: var(--n-ink-3);

  // Un reconditionné se repère d'un coup d'œil : pastille colorée, à part de
  // la promo (accent) et du stock (points).
  &--refurbished {
    display: inline-block;
    padding: 1px 8px;
    border-radius: var(--n-radius-pill);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--n-refurb);
    background: var(--n-refurb-soft);
  }
}

.product-card__stock {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  color: var(--n-ink-2);

  &--order {
    color: var(--n-ink-3);
  }
}

.product-card__offers {
  font-size: 12px;
  color: var(--n-ink-3);
}

.product-card__compare {
  flex-shrink: 0;
  width: 36px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: var(--n-radius);
  background: transparent;
  color: var(--n-ink-3);
  cursor: pointer;
  transition: color 0.2s ease;

  &:hover {
    color: var(--n-ink);
  }

  &--on {
    color: var(--n-accent);
  }
}

.product-card__add {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--n-line-2);
  border-radius: var(--n-radius);
  background: var(--n-surface);
  color: var(--n-ink);
  text-decoration: none;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);

  &:hover:not(:disabled) {
    border-color: var(--n-ink);
  }

  &:active:not(:disabled) {
    transform: translateY(1px) scale(0.97);
  }

  &:disabled {
    border-style: dashed;
    background: transparent;
    color: var(--n-ink-3);
    cursor: not-allowed;
  }
}

@media (max-width: 599px) {
  .product-card {
    gap: 10px;
  }

  .product-card__name {
    font-size: 14px;
  }

  .product-card__ref,
  .product-card__offers {
    display: none;
  }

  .product-card__price {
    font-size: 15px;
  }

  .product-card__stock {
    font-size: 12px;
  }
}
</style>
