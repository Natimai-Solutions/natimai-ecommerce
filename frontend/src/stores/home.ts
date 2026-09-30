import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';

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
  const loaded = ref(false);
  const loading = ref(false);

  async function load(): Promise<void> {
    if (loaded.value || loading.value) return;
    loading.value = true;
    const [featuredResult, popularResult, categoriesResult] = await Promise.allSettled([
      getFeaturedProducts(8),
      getPopularProducts(8, 30),
      getCategories(),
    ]);
    featured.value = featuredResult.status === 'fulfilled' ? featuredResult.value : [];
    const featuredIds = new Set(featured.value.map((p) => p.id));
    popular.value =
      popularResult.status === 'fulfilled'
        ? popularResult.value.filter((p) => !featuredIds.has(p.id))
        : [];
    categories.value =
      categoriesResult.status === 'fulfilled' ? pickCategoryTiles(categoriesResult.value.data) : [];
    loaded.value = [featuredResult, popularResult, categoriesResult].some(
      (r) => r.status === 'fulfilled',
    );
    loading.value = false;
  }

  return { featured, popular, categories, loaded, loading, load };
});
