import { api } from '@/boot/api';

/** `GET /system/config` — territory profile and mode of this deployment (no secrets). */
export interface ShopConfig {
  shop_mode: 'full' | 'simple';
  territory_profile: string;
  territory_label: string;
  reference_currency: string;
  country_code: string;
  tax_territory_code: string;
  shop_name: string;
  /** État réel de chaque module activable (Admin → Modules). */
  modules?: Record<string, boolean>;
  /** Langue par défaut et langues proposées (R7). */
  default_locale?: string;
  available_locales?: string[];
  /** Fuseau horaire des dates affichées. */
  timezone?: string;
  default_display_currency?: string;
}

export async function getShopConfig(): Promise<ShopConfig> {
  const { data } = await api.get<ShopConfig>('/system/config');
  return data;
}
