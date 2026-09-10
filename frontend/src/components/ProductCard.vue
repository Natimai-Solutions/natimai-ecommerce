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
      <div v-if="product.is_featured" class="absolute-top-left q-pa-xs">
        <q-badge color="primary" label="Coup de cœur" />
      </div>
      <div v-if="isOutOfStock" class="absolute-top-right q-pa-xs">
        <q-badge color="grey-6" label="Sur commande" />
      </div>
      <div v-if="offersCount > 1" class="absolute-bottom-right q-pa-xs">
        <q-badge color="teal" :label="`${offersCount} offres`">
          <q-tooltip
            >Même article chez {{ offersCount }} fournisseurs — meilleur prix affiché</q-tooltip
          >
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
      <div class="text-caption q-mt-xs" :class="isOutOfStock ? 'text-grey-6' : 'text-positive'">
        <q-icon name="inventory_2" size="14px" class="q-mr-xs" />
        <span v-if="isOutOfStock">Sur commande</span>
        <span v-else>{{ stockQuantity }} en stock</span>
        <span v-if="variantsCount > 1" class="text-grey-7">
          · {{ variantsCount }} déclinaisons</span
        >
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
        v-if="product.has_variants"
        unelevated
        data-testid="product-choose-variant"
        color="primary"
        icon="tune"
        label="Choisir"
        size="sm"
        :to="productRoute"
      />
      <q-btn
        v-else
        unelevated
        data-testid="product-add-to-cart"
        color="primary"
        icon="add_shopping_cart"
        label="Ajouter"
        size="sm"
        :disable="isOutOfStock"
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
import { sellableQuantity } from 'src/api/products';
import ProductDetailsDialog from 'src/components/ProductDetailsDialog.vue';
import { getProductRoute } from 'src/utils/productRoute';
import { useCurrencyStore } from 'src/stores/currency';

// `offers_count` is served by the backend (search grouping of the same item
// sold by several suppliers) but the generated schema may lag — read it loosely.
type ProductPublic = components['schemas']['ProductPublic'] & { offers_count?: number };

const props = defineProps<{ product: ProductPublic }>();
const offersCount = computed(() => props.product.offers_count ?? 1);
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic] }>();

const currencyStore = useCurrencyStore();
const placeholderImg = '/icons/placeholder-product.svg';
const showDetails = ref(false);
const productRoute = computed(() => getProductRoute(props.product));

const stockQuantity = computed(() => sellableQuantity(props.product));
const isOutOfStock = computed(() => stockQuantity.value <= 0);

const displayPrice = computed(() => {
  const price = parseFloat(props.product.base_price);
  if (price === 0) return '—';
  const formatted = currencyStore.format(price);
  return props.product.has_variants ? `À partir de ${formatted}` : formatted;
});
const variantsCount = computed(() => props.product.variants_count ?? 0);
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
