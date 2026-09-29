import { api } from 'src/boot/api';

/** `GET /system/config` — territory profile and mode of this deployment (no secrets). */
export interface ShopConfig {
  shop_mode: 'full' | 'simple';
  territory_profile: string;
  territory_label: string;
  reference_currency: string;
  country_code: string;
  tax_territory_code: string;
  shop_name: string;
}

export async function getShopConfig(): Promise<ShopConfig> {
  const { data } = await api.get<ShopConfig>('/system/config');
  return data;
}
