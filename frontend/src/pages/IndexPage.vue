<template>
  <q-page class="home">
    <section class="home-hero page-container" aria-labelledby="home-hero-title">
      <div class="home-hero__copy">
        <h1 id="home-hero-title" class="home-hero__title">Le bon matériel, au prix affiché.</h1>
        <p class="home-hero__lead">
          Prix, disponibilité et délai figurent sur chaque fiche. Commandez en ligne ou demandez un
          devis depuis votre panier.
        </p>
        <div class="home-hero__actions">
          <q-btn
            unelevated
            color="primary"
            label="Voir le catalogue"
            icon-right="ph:arrow-right"
            :to="{ name: 'catalogue' }"
            class="home-hero__cta"
          />
        </div>
      </div>
    </section>

    <AppNotice v-if="cartError" tone="error" class="page-container home__notice">
      {{ cartError }}
    </AppNotice>

    <section
      v-if="home.categories.length"
      class="home-section page-container"
      aria-labelledby="home-categories-title"
    >
      <div class="home-section__head">
        <h2 id="home-categories-title" class="home-section__title">Catégories</h2>
        <router-link :to="{ name: 'catalogue' }" class="home-section__link">
          Tout le catalogue
          <q-icon name="ph:arrow-right" size="16px" />
        </router-link>
      </div>
      <ul class="category-tiles">
        <li v-for="category in home.categories" :key="category.id">
          <router-link
            :to="{ name: 'catalogue', query: { cat: category.id } }"
            class="category-tile"
            data-testid="home-category"
          >
            <span class="category-tile__media">
              <img
                v-if="category.image_url"
                :src="category.image_url"
                :alt="''"
                loading="lazy"
                decoding="async"
                class="category-tile__img"
              />
              <q-icon v-else name="ph:squares-four" size="32px" class="category-tile__glyph" />
            </span>
            <span class="category-tile__name">{{ categoryTitle(category) }}</span>
          </router-link>
        </li>
      </ul>
    </section>

    <section
      v-if="home.featured.length"
      class="home-section page-container"
      aria-labelledby="home-featured-title"
    >
      <div class="home-section__head">
        <h2 id="home-featured-title" class="home-section__title">Nos coups de cœur</h2>
      </div>
      <div class="product-grid" data-testid="home-featured">
        <ProductCard
          v-for="product in home.featured"
          :key="product.id"
          :product="product"
          @add-to-cart="onAddToCart"
        />
      </div>
    </section>

    <section
      v-if="home.popular.length"
      class="home-section page-container"
      aria-labelledby="home-popular-title"
    >
      <div class="home-section__head">
        <h2 id="home-popular-title" class="home-section__title">Les plus consultés</h2>
        <span class="home-section__hint">ces 30 derniers jours</span>
      </div>
      <div class="product-grid" data-testid="home-popular">
        <ProductCard
          v-for="product in home.popular"
          :key="product.id"
          :product="product"
          @add-to-cart="onAddToCart"
        />
      </div>
    </section>

    <section v-if="showSkeleton" class="home-section page-container" aria-busy="true">
      <div class="product-grid">
        <div v-for="n in 4" :key="n" class="skeleton-card">
          <q-skeleton square class="skeleton-card__media" />
          <q-skeleton type="text" width="40%" />
          <q-skeleton type="text" width="90%" />
        </div>
      </div>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onServerPrefetch, ref } from 'vue';
import { useMeta } from 'quasar';
import type { components } from '@app/api-types';

import AppNotice from '@/components/AppNotice.vue';
import ProductCard from '@/components/ProductCard.vue';
import { useCartStore } from '@/stores/cart';
import { categoryTitle, useHomeStore } from '@/stores/home';
import { useUiStore } from '@/stores/ui';

type ProductPublic = components['schemas']['ProductPublic'];

const home = useHomeStore();
const cartStore = useCartStore();
const uiStore = useUiStore();
const cartError = ref<string | null>(null);

useMeta({
  title: 'Accueil | Natimai',
  meta: {
    description: {
      name: 'description',
      content:
        'Matériel informatique : prix, disponibilité et délai affichés sur chaque fiche. Commande en ligne ou sur devis.',
    },
  },
});

// Tant que rien n'est arrivé, des squelettes gardent la place des produits.
const showSkeleton = computed(() => !home.loaded && !home.featured.length && !home.popular.length);

async function onAddToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? "Impossible d'ajouter cet article au panier.";
}

onServerPrefetch(() => home.load());
onMounted(() => home.load());
</script>

<style scoped lang="scss">
.home {
  padding-bottom: 96px;
}

.home-hero {
  padding-top: 72px;
  padding-bottom: 56px;

  @media (max-width: 767px) {
    padding-top: 40px;
    padding-bottom: 32px;
  }
}

.home-hero__copy {
  max-width: 720px;
}

.home-hero__title {
  margin: 0;
  font-size: clamp(36px, 5vw, 60px);
  font-weight: 600;
  line-height: 1.02;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.home-hero__lead {
  max-width: 56ch;
  margin: 20px 0 0;
  font-size: 17px;
  line-height: 1.55;
  color: var(--n-ink-2);
  text-wrap: pretty;
}

.home-hero__actions {
  margin-top: 32px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.home-hero__cta {
  min-height: 48px;
  padding: 0 22px;
}

.home__notice {
  margin-bottom: 24px;
}

.home-section {
  padding-top: 48px;
  border-top: 1px solid var(--n-line);
  margin-top: 8px;

  & + & {
    margin-top: 56px;
  }
}

.home-section__head {
  margin-bottom: 24px;
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.home-section__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.015em;
}

.home-section__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}

.home-section__link {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.category-tiles {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  // auto-fit : les tuiles s'étirent sur la ligne, sans orpheline quand il y
  // en a 5 ou 7.
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 20px;

  // Mobile : une rangée qui défile, plutôt qu'une grille à tuile orpheline.
  @media (max-width: 599px) {
    grid-auto-flow: column;
    grid-template-columns: none;
    grid-auto-columns: 42%;
    gap: 12px;
    margin-right: -16px;
    padding-right: 16px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;

    > li {
      scroll-snap-align: start;
    }
  }
}

.category-tile {
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--n-ink);
  text-decoration: none;

  &:hover .category-tile__media {
    background: var(--n-tile-hover);
  }

  &:hover .category-tile__img {
    transform: scale(1.03);
  }

  &:hover .category-tile__name {
    color: var(--n-accent);
  }
}

.category-tile__media {
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 8px;
  background: var(--n-tile);
  transition: background-color 0.2s ease;
}

.category-tile__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.category-tile__glyph {
  color: var(--n-glyph);
}

.category-tile__name {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.3;
  transition: color 0.2s ease;
}
</style>
