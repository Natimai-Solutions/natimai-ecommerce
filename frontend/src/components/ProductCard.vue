<template>
  <article class="product-card" data-testid="product-card">
    <router-link :to="productRoute" class="product-card__media" tabindex="-1" aria-hidden="true">
      <ProductImage :src="imageUrl" :alt="product.name" />
    </router-link>

    <div class="product-card__info">
      <span class="product-card__brand">
        {{ brand
        }}<template v-if="refurbished">
          <span v-if="brand" aria-hidden="true"> · </span>
          <span class="product-card__condition" data-testid="product-condition">{{
            conditionLabel(product)
          }}</span>
        </template>
      </span>
      <router-link :to="productRoute" class="product-card__name">{{ product.name }}</router-link>
      <span v-if="product.vendor_part_number" class="product-card__ref font-mono">
        {{ product.vendor_part_number }}
      </span>
    </div>

    <div class="product-card__buy">
      <div class="product-card__meta">
        <span v-if="isQuote" class="product-card__price">Prix sur devis</span>
        <span v-else class="product-card__price">
          <span v-if="product.has_variants" class="product-card__from">À partir de</span>
          <span class="font-mono">{{ displayPrice }}</span>
          <span class="product-card__tax">TTC</span>
        </span>

        <span
          class="product-card__stock"
          :class="{
            'product-card__stock--order': availability.preorder || !availability.orderable,
          }"
        >
          <span
            class="stock-dot"
            :class="{ 'stock-dot--order': availability.preorder || !availability.orderable }"
            aria-hidden="true"
          />{{ availability.label }}
        </span>
        <span v-if="departureStore.deliveryLabel" class="product-card__offers">
          {{ departureStore.deliveryLabel }}
        </span>

        <span v-if="variantsCount > 1" class="product-card__offers">
          {{ variantsCount }} déclinaisons
        </span>

        <span v-if="offersCount > 1" class="product-card__offers">
          {{ offersCount }} offres, meilleur prix affiché
        </span>
      </div>

      <router-link
        v-if="product.has_variants"
        :to="productRoute"
        class="product-card__add"
        data-testid="product-choose-variant"
        :aria-label="`Choisir une déclinaison de ${product.name}`"
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
            ? `Ajouter ${product.name} au panier`
            : 'Indisponible pour le moment'
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
import { useCurrencyStore } from '@/stores/currency';
import { useDepartureStore } from '@/stores/departure';
import { conditionLabel, isRefurbished, productAvailability } from '@/utils/availability';

// `offers_count` is served by the backend (search grouping of the same item
// sold by several suppliers) but the generated schema may lag — read it loosely.
type ProductPublic = components['schemas']['ProductPublic'] & { offers_count?: number };

const props = defineProps<{ product: ProductPublic }>();
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic] }>();

const currencyStore = useCurrencyStore();

const offersCount = computed(() => props.product.offers_count ?? 1);
const productRoute = computed(() => getProductRoute(props.product));
const imageUrl = computed(() => props.product.image_url ?? props.product.supplier_image_url);
const brand = computed(() => props.product.manufacturer ?? props.product.supplier_name ?? '');

const departureStore = useDepartureStore();
const availability = computed(() => productAvailability(props.product));
const refurbished = computed(() => isRefurbished(props.product));
const variantsCount = computed(() => props.product.variants_count ?? 0);

const isQuote = computed(() => parseFloat(props.product.base_price) === 0);
// A parent is listed at its cheapest variant, prefixed « À partir de ».
const displayPrice = computed(() => currencyStore.format(parseFloat(props.product.base_price)));
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
  color: var(--n-ink);
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

.product-card__add {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--n-line-2);
  border-radius: 8px;
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

@media (max-width: 767px) {
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
