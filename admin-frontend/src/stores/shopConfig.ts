import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { getShopConfig, type ShopConfig } from '@/api/shopConfig';

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

  /**
   * Whether a switchable module is on. Unknown (config not loaded, older
   * API) counts as on: hiding a screen by mistake is worse than showing one.
   */
  function moduleOn(key: string): boolean {
    return config.value?.modules?.[key] ?? true;
  }

  /** Re-read the config after a module switch (the menus follow at once). */
  async function reload(): Promise<void> {
    loaded.value = false;
    await load();
  }

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

  return { config, loaded, isSimple, currency, territoryLabel, moduleOn, load, reload };
});
