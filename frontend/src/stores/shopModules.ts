import { defineStore } from 'pinia';
import { ref } from 'vue';
import { configureFormatting } from '@app/utils';

import { api } from '@/boot/api';

/** What `GET /system/config` tells every visitor (no secrets). */
export interface ShopPublicConfig {
  shop_name?: string;
  reference_currency?: string;
  /** ISO country of the shop: its zone tree (islands) is the destination list. */
  country_code?: string;
  modules?: Record<string, boolean>;
  /** Language when the visitor states none, and the languages offered (R7). */
  default_locale?: string;
  available_locales?: string[];
  /** IANA time zone of the dates shown to customers. */
  timezone?: string;
  /** Display currency proposed to a visitor who chose none. */
  default_display_currency?: string;
  /** Cloudflare Turnstile site key of the public forms; null = no captcha. */
  captcha_site_key?: string | null;
  /** Logo and site icon chosen in the back-office (R9 / T9). */
  branding?: {
    logo?: { src: string; srcset?: string | null; width: number; height: number } | null;
    icon?: { base: string; sizes: number[]; manifest: string } | null;
  };
}

/**
 * Shop configuration (`GET /system/config`): switched-on modules, languages,
 * time zone, default display currency. The storefront hides what belongs to
 * a switched-off module; an unknown module — config not loaded yet, older
 * API — counts as on: hiding a feature by mistake is worse than showing one.
 */
export const useShopModulesStore = defineStore('shopModules', () => {
  const modules = ref<Record<string, boolean>>({});
  const config = ref<ShopPublicConfig>({});
  const loaded = ref(false);

  function isOn(key: string): boolean {
    return modules.value[key] ?? true;
  }

  /** The shop's zone for dates — in the browser too (audit 2026-11): the
   *  state hydrated from the server render made `load()` return early, and
   *  the client kept formatting in the default zone. */
  function applyFormatting(): void {
    if (config.value.timezone) configureFormatting({ timeZone: config.value.timezone });
  }

  async function load(): Promise<void> {
    if (loaded.value) {
      applyFormatting();
      return;
    }
    try {
      const { data } = await api.get<ShopPublicConfig>('/system/config');
      config.value = data;
      modules.value = data.modules ?? {};
      applyFormatting();
      // Set on success only: a failed server render must let the browser retry.
      loaded.value = true;
    } catch {
      // non-critical: everything stays visible
    }
  }

  return { modules, config, loaded, isOn, load };
});
