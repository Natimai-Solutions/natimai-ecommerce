import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';

import { getHomepage, type HomepageBlock } from '@/api/homepage';
import { getCategories, getFeaturedProducts, getPopularProducts } from '@/api/products';
import { pickCategoryTiles } from '@/utils/categories';

export { categoryTitle } from '@/utils/categories';

type ProductPublic = components['schemas']['ProductPublic'];
type CategoryPublic = components['schemas']['CategoryPublic'];

/**
 * Données de la page d'accueil, dans un store pour que le rendu serveur les
 * transmette au navigateur (un `ref` local de composant serait refetché à
 * l'hydratation, avec un saut d'affichage).
 *
 * Chaque section échoue seule : un classement vide ne masque pas les
 * vedettes. `loaded` n'est posé qu'après au moins une réponse, pour qu'un
 * échec du rendu serveur laisse le navigateur réessayer.
 */
export const useHomeStore = defineStore('home', () => {
  const featured = ref<ProductPublic[]>([]);
  const popular = ref<ProductPublic[]>([]);
  const categories = ref<CategoryPublic[]>([]);
  // Hero et bannières saisis dans l'admin (Accueil du site).
  const hero = ref<HomepageBlock | null>(null);
  const banners = ref<HomepageBlock[]>([]);
  const loaded = ref(false);
  const loading = ref(false);
  /** Every call failed (API down): the page offers to try again instead of
   *  an endless skeleton (audit 2026-11, U8). */
  const failed = ref(false);

  async function load(): Promise<void> {
    if (loaded.value || loading.value) return;
    loading.value = true;
    const [featuredResult, popularResult, categoriesResult, blocksResult] =
      await Promise.allSettled([
        getFeaturedProducts(8),
        getPopularProducts(8, 30),
        getCategories(),
        getHomepage(),
      ]);
    hero.value = blocksResult.status === 'fulfilled' ? (blocksResult.value.hero ?? null) : null;
    banners.value = blocksResult.status === 'fulfilled' ? (blocksResult.value.banners ?? []) : [];
    featured.value = featuredResult.status === 'fulfilled' ? featuredResult.value : [];
    const featuredIds = new Set(featured.value.map((p) => p.id));
    popular.value =
      popularResult.status === 'fulfilled'
        ? popularResult.value.filter((p) => !featuredIds.has(p.id))
        : [];
    categories.value =
      categoriesResult.status === 'fulfilled' ? pickCategoryTiles(categoriesResult.value.data) : [];
    loaded.value = [featuredResult, popularResult, categoriesResult, blocksResult].some(
      (r) => r.status === 'fulfilled',
    );
    failed.value = !loaded.value;
    loading.value = false;
  }

  /** Fetch again (the visitor switched language: texts follow it, R9 / T3). */
  async function reload(): Promise<void> {
    loaded.value = false;
    await load();
  }

  return { featured, popular, categories, hero, banners, loaded, loading, failed, load, reload };
});
