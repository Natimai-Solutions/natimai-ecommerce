import { defineStore } from 'pinia';
import { ref } from 'vue';

/** État d'interface partagé entre la mise en page et les pages. */
export const useUiStore = defineStore('ui', () => {
  const cartDrawerOpen = ref(false);
  /** Article qui vient d'être ajouté : le mini-panier le confirme en tête. */
  const lastAddedProductId = ref<string | null>(null);

  function openCartDrawer(addedProductId: string | null = null) {
    lastAddedProductId.value = addedProductId;
    cartDrawerOpen.value = true;
  }

  function closeCartDrawer() {
    cartDrawerOpen.value = false;
  }

  return { cartDrawerOpen, lastAddedProductId, openCartDrawer, closeCartDrawer };
});
