import { defineStore } from 'pinia';
import { ref } from 'vue';

import { api } from '@/boot/api';

/**
 * Modules switched on or off from the back-office (`GET /system/config` →
 * `modules`). The storefront hides what belongs to a switched-off module;
 * an unknown module — config not loaded yet, older API — counts as on:
 * hiding a feature by mistake is worse than showing one.
 */
export const useShopModulesStore = defineStore('shopModules', () => {
  const modules = ref<Record<string, boolean>>({});
  const loaded = ref(false);

  function isOn(key: string): boolean {
    return modules.value[key] ?? true;
  }

  async function load(): Promise<void> {
    if (loaded.value) return;
    try {
      const { data } = await api.get<{ modules?: Record<string, boolean> }>('/system/config');
      modules.value = data.modules ?? {};
      // Set on success only: a failed server render must let the browser retry.
      loaded.value = true;
    } catch {
      // non-critical: everything stays visible
    }
  }

  return { modules, loaded, isOn, load };
});
