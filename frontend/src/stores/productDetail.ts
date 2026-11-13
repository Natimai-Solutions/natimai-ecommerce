import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';

import { getProductById, getProductVariants, type ProductVariantsResponse } from '@/api/products';
import { apiErrorMessage } from '@/utils/errors';

type ProductPublic = components['schemas']['ProductPublic'];

/**
 * Le produit de la fiche, dans un store pour que le rendu serveur le
 * transmette au navigateur. Dans un `ref` local, le navigateur hydratait
 * une page sans produit (squelette, puis second appel identique) contre le
 * HTML complet du serveur : saut d'affichage et décalage d'hydratation sur
 * la page qui compte le plus pour le référencement.
 *
 * `loadedKey` (produit et langue) dit ce que le store contient et
 * `fromServer` qu'il vient du rendu serveur : à l'hydratation, la même
 * fiche n'est pas rechargée. Une navigation suivante recharge toujours
 * (stock et prix frais).
 */
export const useProductDetailStore = defineStore('productDetail', () => {
  const product = ref<ProductPublic | null>(null);
  const variants = ref<ProductVariantsResponse | null>(null);
  /** `not_found`, sinon le message de l'erreur (le libellé vient de la page). */
  const error = ref<string | null>(null);
  const loading = ref(true);
  const loadedKey = ref<string | null>(null);
  const fromServer = ref(false);
  /**
   * Only the latest load writes (audit 2026-11, F2): A then B quickly, A's
   * answer arriving last used to put product A on page B — whose skeleton
   * then waited forever for B.
   */
  let latest = 0;

  async function load(productId: string, locale: string): Promise<void> {
    const key = `${productId}|${locale}`;
    if (fromServer.value) {
      // First client call after the server render: what it sent is current.
      fromServer.value = false;
      if (loadedKey.value === key && !loading.value) return;
    }
    const call = ++latest;
    loading.value = true;
    error.value = null;
    try {
      const data = await getProductById(productId);
      let found: ProductVariantsResponse | null = null;
      if (data.has_variants) {
        found = await getProductVariants(productId).catch(() => null);
      }
      if (call !== latest) return;
      product.value = data;
      variants.value = found;
      loadedKey.value = key;
      fromServer.value = Boolean(import.meta.env.QUASAR_SERVER);
    } catch (e) {
      if (call !== latest) return;
      product.value = null;
      variants.value = null;
      // A failure is not cached: the next visit (or the browser after a
      // failed server render) tries again.
      loadedKey.value = null;
      const status = (e as { response?: { status?: number } }).response?.status;
      // The API's own message, never axios' « Request failed with status
      // code 503 » (audit 2026-11, U2): « unknown » lets the page say it.
      error.value = status === 404 ? 'not_found' : (apiErrorMessage(e) ?? 'unknown');
    } finally {
      if (call === latest) loading.value = false;
    }
  }

  /** No id in the route: nothing to show, a « not found » page. */
  function notFound(): void {
    latest += 1; // a load still on its way no longer writes
    product.value = null;
    variants.value = null;
    loadedKey.value = null;
    error.value = 'not_found';
    loading.value = false;
  }

  return { product, variants, error, loading, loadedKey, fromServer, load, notFound };
});
