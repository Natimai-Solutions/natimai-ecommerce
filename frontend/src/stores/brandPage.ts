import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';

import { getBrandPage, type BrandPage } from '@/api/brands';
import { searchProducts } from '@/api/products';
import { apiErrorMessage } from '@/utils/errors';

type ProductPublic = components['schemas']['ProductPublic'];

/** Produits montrés sur la page d'une marque, les plus récents d'abord. */
export const BRAND_PAGE_PRODUCTS = 24;

/**
 * La page d'une marque (lot BR), dans un store pour que le rendu serveur la
 * transmette au navigateur (comme la fiche produit) : pas de second appel ni
 * de décalage d'hydratation sur une page faite pour le référencement.
 */
export const useBrandPageStore = defineStore('brandPage', () => {
  const brand = ref<BrandPage | null>(null);
  const products = ref<ProductPublic[]>([]);
  /** Entries listed (variants grouped under their product), not raw rows. */
  const total = ref(0);
  /** `not_found`, sinon le message de l'erreur. */
  const error = ref<string | null>(null);
  const loading = ref(true);
  const loadedSlug = ref<string | null>(null);
  let latest = 0;

  async function load(slug: string): Promise<void> {
    if (loadedSlug.value === slug && !loading.value && brand.value) return;
    const call = ++latest;
    loading.value = true;
    error.value = null;
    try {
      const found = await getBrandPage(slug);
      const result = await searchProducts({
        brand_id: found.id,
        limit: BRAND_PAGE_PRODUCTS,
        offset: 0,
        sort: 'newest',
        group_offers: true,
      });
      if (call !== latest) return;
      brand.value = found;
      products.value = result.data ?? [];
      total.value = result.count ?? 0;
      loadedSlug.value = slug;
    } catch (e) {
      if (call !== latest) return;
      brand.value = null;
      products.value = [];
      total.value = 0;
      loadedSlug.value = null;
      const status = (e as { response?: { status?: number } }).response?.status;
      error.value = status === 404 ? 'not_found' : (apiErrorMessage(e) ?? 'unknown');
    } finally {
      if (call === latest) loading.value = false;
    }
  }

  return { brand, products, total, error, loading, loadedSlug, load };
});
