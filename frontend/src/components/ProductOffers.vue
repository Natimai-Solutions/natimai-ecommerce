<template>
  <div v-if="others.length > 0" class="product-offers">
    <div class="text-subtitle2 q-mb-xs">
      {{ others.length === 1 ? 'Autre offre' : `${others.length} autres offres` }}
      <span class="text-caption text-grey-6"> — même article, autre fournisseur</span>
    </div>
    <q-list bordered separator dense class="rounded-borders">
      <q-item
        v-for="offer in others"
        :key="offer.product_id"
        clickable
        :to="getProductRouteByIdAndName(offer.product_id, offer.name)"
        @click="emit('navigate')"
      >
        <q-item-section avatar>
          <q-avatar rounded size="40px" class="bg-grey-1">
            <img
              v-if="offer.image_url"
              :src="offer.image_url"
              :alt="offer.name"
              style="object-fit: contain"
            />
            <q-icon v-else name="inventory_2" color="grey-5" />
          </q-avatar>
        </q-item-section>
        <q-item-section>
          <q-item-label class="ellipsis">{{ offer.supplier_label ?? offer.name }}</q-item-label>
          <q-item-label caption>
            <q-badge
              :color="offer.is_domestic ? 'teal' : 'orange'"
              :label="offer.is_domestic ? 'Stock local' : 'Import'"
              class="q-mr-xs"
            />
            <span :class="offer.in_stock ? 'text-positive' : 'text-grey-6'">
              {{ offer.in_stock ? `${stockOf(offer)} en stock` : 'Sur commande' }}
            </span>
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div class="text-weight-bold text-primary">{{ priceOf(offer) }}</div>
          <q-badge v-if="offer.product_id === cheapestId" color="positive" label="Meilleur prix" />
        </q-item-section>
      </q-item>
    </q-list>
    <div v-if="currentIsCheapest" class="text-caption text-positive q-mt-xs">
      <q-icon name="check_circle" size="14px" class="q-mr-xs" />Cette offre est la moins chère.
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { sellableQuantity } from 'src/api/products';
import type { ProductOfferPublic, ProductOffersResponse } from 'src/api/products';
import { useCurrencyStore } from 'src/stores/currency';
import { getProductRouteByIdAndName } from 'src/utils/productRoute';

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

function stockOf(offer: ProductOfferPublic): number {
  return sellableQuantity(offer);
}
</script>
