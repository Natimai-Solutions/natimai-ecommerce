<template>
  <q-page padding>
    <section class="hero q-pa-lg q-mb-lg rounded-borders">
      <div class="text-h4 text-weight-bold">Bienvenue</div>
      <div class="text-body1 text-grey-8 q-mt-sm">
        Matériel informatique et consommables, en stock à Tahiti ou importés à la demande.
      </div>
      <q-btn
        class="q-mt-md"
        color="primary"
        label="Voir le catalogue"
        icon="storefront"
        unelevated
        :to="{ name: 'catalogue' }"
      />
    </section>

    <q-banner
      v-if="cartFeedback"
      dense
      rounded
      class="q-mb-md"
      :class="cartFeedback.ok ? 'bg-green-1 text-green-9' : 'bg-red-1 text-red-9'"
    >
      {{ cartFeedback.message }}
    </q-banner>

    <section v-if="featured.length" class="q-mb-xl">
      <div class="row items-center q-mb-sm">
        <div class="text-h6 col">Nos coups de cœur</div>
      </div>
      <div class="row q-col-gutter-md">
        <div
          v-for="product in featured"
          :key="product.id"
          class="col-12 col-sm-6 col-md-4 col-lg-3"
        >
          <ProductCard :product="product" @add-to-cart="onAddToCart" />
        </div>
      </div>
    </section>

    <section v-if="popular.length" class="q-mb-xl">
      <div class="row items-center q-mb-sm">
        <div class="text-h6 col">Les plus consultés</div>
        <div class="text-caption text-grey-7">ces 30 derniers jours</div>
      </div>
      <div class="row q-col-gutter-md">
        <div v-for="product in popular" :key="product.id" class="col-12 col-sm-6 col-md-4 col-lg-3">
          <ProductCard :product="product" @add-to-cart="onAddToCart" />
        </div>
      </div>
    </section>

    <div v-if="loading" class="row q-col-gutter-md">
      <div v-for="n in 4" :key="n" class="col-12 col-sm-6 col-md-4 col-lg-3">
        <q-skeleton type="rect" height="260px" />
      </div>
    </div>

    <div
      v-else-if="!featured.length && !popular.length"
      class="text-body1 text-grey-7 text-center q-pa-xl"
    >
      Le catalogue vous attend.
      <q-btn flat color="primary" label="Le parcourir" :to="{ name: 'catalogue' }" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, onServerPrefetch, ref } from 'vue';
import type { components } from '@app/api-types';
import ProductCard from 'src/components/ProductCard.vue';
import { getFeaturedProducts, getPopularProducts } from 'src/api/products';
import { useCartStore } from 'src/stores/cart';

type ProductPublic = components['schemas']['ProductPublic'];

const cartStore = useCartStore();
const featured = ref<ProductPublic[]>([]);
const popular = ref<ProductPublic[]>([]);
const loading = ref(true);
const cartFeedback = ref<{ ok: boolean; message: string } | null>(null);

async function load() {
  loading.value = true;
  // Each section fails on its own: an empty ranking must not hide the featured ones.
  const [featuredResult, popularResult] = await Promise.allSettled([
    getFeaturedProducts(8),
    getPopularProducts(8, 30),
  ]);
  featured.value = featuredResult.status === 'fulfilled' ? featuredResult.value : [];
  const featuredIds = new Set(featured.value.map((p) => p.id));
  popular.value =
    popularResult.status === 'fulfilled'
      ? popularResult.value.filter((p) => !featuredIds.has(p.id))
      : [];
  loading.value = false;
}

async function onAddToCart(product: ProductPublic) {
  cartFeedback.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  cartFeedback.value = ok
    ? { ok: true, message: `${product.name} ajouté au panier.` }
    : { ok: false, message: cartStore.error ?? "Impossible d'ajouter cet article au panier." };
}

onServerPrefetch(load);
onMounted(async () => {
  if (loading.value) await load();
});
</script>

<style scoped>
.hero {
  background: linear-gradient(135deg, #e8f0fa 0%, #f6f8fb 100%);
}
</style>
