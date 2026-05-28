<template>
  <q-card class="product-card" flat bordered>
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
        :class="isOutOfStock ? 'text-grey-6' : 'text-positive'"
      >
        <q-icon name="inventory_2" size="14px" class="q-mr-xs" />
        <span v-if="isOutOfStock">Sur commande</span>
        <span v-else>{{ stockQuantity }} en stock</span>
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
        unelevated
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
import { computed, ref } from 'vue'
import type { components } from '@app/api-types'
import { formatXpf } from '@app/utils'
import ProductDetailsDialog from 'src/components/ProductDetailsDialog.vue'

type ProductPublic = components['schemas']['ProductPublic']

const props = defineProps<{ product: ProductPublic }>()
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic] }>()

const placeholderImg = '/icons/placeholder-product.svg'
const showDetails = ref(false)

const isOutOfStock = computed(() => parseFloat(props.product.supplier_quantity) <= 0)

const stockQuantity = computed(() =>
  Math.max(0, Math.round(parseFloat(props.product.supplier_quantity))),
)

const displayPrice = computed(() => {
  const price = parseFloat(props.product.base_price)
  if (price === 0) return '—'
  return formatXpf(price)
})
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
