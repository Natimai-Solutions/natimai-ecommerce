import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { getShopConfig, type ShopConfig } from 'src/api/shopConfig';

/**
 * Deployment-level facts every admin screen may need: the reference
 * currency for labels, and the shop mode that decides which menus and form
 * sections are shown. Loaded once; a failure keeps the full-featured defaults.
 */
export const useShopConfigStore = defineStore('shopConfig', () => {
  const config = ref<ShopConfig | null>(null);
  const loaded = ref(false);

  const isSimple = computed(() => config.value?.shop_mode === 'simple');
  const currency = computed(() => config.value?.reference_currency ?? 'XPF');
  const territoryLabel = computed(() => config.value?.territory_label ?? '');

  async function load(): Promise<void> {
    if (loaded.value) return;
    try {
      config.value = await getShopConfig();
    } catch {
      config.value = null;
    } finally {
      loaded.value = true;
    }
  }

  return { config, loaded, isSimple, currency, territoryLabel, load };
});
