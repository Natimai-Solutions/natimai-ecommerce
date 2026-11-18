import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';

import { accessToken } from '@/boot/api';
import {
  getHomepage,
  getPersonalHomepage,
  type HomepageContent,
  type HomepageSection,
} from '@/api/homepage';
import { getCategories } from '@/api/products';
import { pickCategoryTiles } from '@/utils/categories';

export { categoryTitle } from '@/utils/categories';

type CategoryPublic = components['schemas']['CategoryPublic'];

function currentAudience(): 'guest' | 'account' {
  return accessToken.value ? 'account' : 'guest';
}

/**
 * Données de la page d'accueil, dans un store pour que le rendu serveur les
 * transmette au navigateur (un `ref` local de composant serait refetché à
 * l'hydratation, avec un saut d'affichage).
 *
 * L'accueil est une liste ordonnée de sections, réglée dans l'admin (héros,
 * bannières, catégories, coups de cœur, plus consultés), chacune pour un
 * public (chantier accueil et messagerie, R1 et R8). Le serveur rend la page
 * du visiteur ; un client connecté reçoit la sienne (ses sections, ses prix)
 * depuis le navigateur.
 *
 * Les tuiles de catégories viennent de leur propre appel : la page reste
 * affichable si l'un des deux échoue. `loaded` n'est posé qu'après au moins
 * une réponse, pour qu'un échec du rendu serveur laisse le navigateur
 * réessayer.
 */
export const useHomeStore = defineStore('home', () => {
  const sections = ref<HomepageSection[]>([]);
  const categories = ref<CategoryPublic[]>([]);
  const loaded = ref(false);
  const loading = ref(false);
  /** Every call failed (API down): the page offers to try again instead of
   *  an endless skeleton (audit 2026-11, U8). */
  const failed = ref(false);
  /**
   * Whose page the sections are: the server render is always anonymous, so
   * a customer arriving signed in, or signing in / out on the page, gets
   * their own (sections of their audience, prices of their group).
   */
  const pageFor = ref<'guest' | 'account'>('guest');

  function pageRequest(): Promise<HomepageContent> {
    return currentAudience() === 'account' ? getPersonalHomepage() : getHomepage();
  }

  async function load(): Promise<void> {
    if (loaded.value || loading.value) return;
    loading.value = true;
    pageFor.value = currentAudience();
    const [pageResult, categoriesResult] = await Promise.allSettled([
      pageRequest(),
      getCategories(),
    ]);
    sections.value = pageResult.status === 'fulfilled' ? (pageResult.value.sections ?? []) : [];
    categories.value =
      categoriesResult.status === 'fulfilled' ? categoriesResult.value.data : [];
    loaded.value = [pageResult, categoriesResult].some((r) => r.status === 'fulfilled');
    failed.value = !loaded.value;
    loading.value = false;
  }

  /**
   * The page again, for whoever is signed in now, when the sections were
   * someone else's. A failure keeps the page shown.
   */
  async function syncAudience(): Promise<void> {
    if (!loaded.value || loading.value || pageFor.value === currentAudience()) return;
    pageFor.value = currentAudience();
    try {
      sections.value = (await pageRequest()).sections ?? [];
    } catch {
      // The visitor's page stays: better than an empty homepage.
    }
  }

  /** Fetch again (the visitor switched language: texts follow it, R9 / T3). */
  async function reload(): Promise<void> {
    loaded.value = false;
    await load();
  }

  /** The category tiles of a « categories » section. */
  function categoryTiles(limit: number): CategoryPublic[] {
    return pickCategoryTiles(categories.value, limit);
  }

  return {
    sections,
    categories,
    loaded,
    loading,
    failed,
    pageFor,
    load,
    reload,
    syncAudience,
    categoryTiles,
  };
});
