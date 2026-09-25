<template>
  <q-card class="product-card" flat bordered data-testid="product-card">
    <q-img
      :src="product.image_url ?? product.supplier_image_url ?? placeholderImg"
      :ratio="4 / 3"
      fit="cover"
      loading="lazy"
    >
      <template #error>
        <div class="absolute-full flex flex-center bg-grey-2">
          <q-icon name="image_not_supported" size="3rem" color="grey-5" />
        </div>
      </template>
      <div class="absolute-top-left q-pa-xs column q-gutter-xs items-start">
        <q-badge v-if="product.is_featured" color="primary" label="Coup de cœur" />
        <q-badge
          v-if="refurbished"
          color="orange-8"
          :label="conditionLabel(product)"
          data-testid="product-condition"
        />
      </div>
      <div v-if="availability.preorder || !availability.orderable" class="absolute-top-right q-pa-xs">
        <q-badge color="grey-6" :label="availability.label" />
      </div>
      <div v-if="offersCount > 1" class="absolute-bottom-right q-pa-xs">
        <q-badge color="teal" :label="`${offersCount} offres`">
          <q-tooltip>Même article chez {{ offersCount }} fournisseurs — meilleur prix affiché</q-tooltip>
        </q-badge>
      </div>
    </q-img>

    <q-card-section class="q-pb-xs">
      <div class="text-caption text-grey-6 ellipsis">
        {{ product.manufacturer ?? product.supplier_name ?? '&nbsp;' }}
      </div>
      <div class="product-name text-body2 text-weight-medium q-mt-xs">
        {{ product.name }}
      </div>
      <div v-if="product.vendor_part_number" class="text-caption text-grey-5">
        Réf. {{ product.vendor_part_number }}
      </div>
    </q-card-section>

    <q-card-section class="q-pt-xs q-pb-sm">
      <div class="text-h6 text-weight-bold text-primary">
        {{ displayPrice }}
      </div>
      <div v-if="product.base_price === '0.00'" class="text-caption text-grey-6">
        Prix sur devis
      </div>
      <div
        class="text-caption q-mt-xs"
        :class="availability.orderable ? 'text-positive' : 'text-grey-6'"
      >
        <q-icon name="inventory_2" size="14px" class="q-mr-xs" />
        <span>{{ availability.label }}</span>
      </div>
      <div v-if="departureStore.deliveryLabel" class="text-caption text-grey-7">
        {{ departureStore.deliveryLabel }}
      </div>
    </q-card-section>

    <q-separator />

    <q-card-actions align="right">
      <q-btn
        flat
        dense
        color="grey-7"
        icon="info_outline"
        aria-label="Détails"
        @click="showDetails = true"
      />
      <q-btn
        flat
        dense
        color="grey-7"
        icon="open_in_new"
        aria-label="Fiche produit"
        :to="productRoute"
      />
      <q-btn
        unelevated
        data-testid="product-add-to-cart"
        color="primary"
        icon="add_shopping_cart"
        label="Ajouter"
        size="sm"
        :disable="!availability.orderable"
        @click="emit('add-to-cart', product)"
      />
    </q-card-actions>

    <ProductDetailsDialog
      v-model="showDetails"
      :product="product"
      @add-to-cart="emit('add-to-cart', product)"
    />
  </q-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { components } from '@app/api-types';
import ProductDetailsDialog from 'src/components/ProductDetailsDialog.vue';
import { getProductRoute } from 'src/utils/productRoute';
import { useCurrencyStore } from 'src/stores/currency';
import { useDepartureStore } from 'src/stores/departure';
import { conditionLabel, isRefurbished, productAvailability } from 'src/utils/availability';

// `offers_count` is served by the backend (search grouping of the same item
// sold by several suppliers) but the generated schema may lag — read it loosely.
type ProductPublic = components['schemas']['ProductPublic'] & { offers_count?: number };

const props = defineProps<{ product: ProductPublic }>();
const offersCount = computed(() => props.product.offers_count ?? 1);
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic] }>();

const currencyStore = useCurrencyStore();
const departureStore = useDepartureStore();
const placeholderImg = '/icons/placeholder-product.svg';
const showDetails = ref(false);
const productRoute = computed(() => getProductRoute(props.product));

const availability = computed(() => productAvailability(props.product));
const refurbished = computed(() => isRefurbished(props.product));

const displayPrice = computed(() => {
  const price = parseFloat(props.product.base_price);
  if (price === 0) return '—';
  return currencyStore.format(price);
});
</script>

<style scoped lang="scss">
.product-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  transition: box-shadow 0.2s ease;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  }
}

.product-name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 2.8em;
}
</style>
