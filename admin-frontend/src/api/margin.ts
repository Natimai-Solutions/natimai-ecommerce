import { api } from '@/boot/api';

/** Price inputs of the product form, as they stand (unsaved). */
export interface MarginPreviewRequest {
  product_id?: string | null;
  pricing_mode?: string;
  base_price?: string | null;
  cost_amount?: string | null;
  cost_currency?: string | null;
  margin_rate_pct?: string | null;
  customs_rate_pct?: string | null;
  tax_rate_id?: string | null;
  category_id?: string | null;
  /** Prix saisis par groupe dans le formulaire (absent : ceux enregistrés). */
  group_prices?: Record<string, string> | null;
}

/** Ce qu'un groupe de clients paie pour l'article, et la marge qui reste. */
export interface GroupPriceLine {
  price_group_id: string;
  label: string;
  is_default: boolean;
  discount_pct: string;
  /** Prix saisi pour le groupe (null : la remise s'applique). */
  typed_price: string | null;
  /** Prix payé : saisi, sinon référence − remise. */
  price: string | null;
  margin_amount: string | null;
  margin_pct: string | null;
}

/** What one unit sells for, what it costs and what is left (server figures). */
export interface MarginPreview {
  price_incl_tax: string | null;
  tax_rate_pct: string;
  price_excl_tax: string | null;
  tax_amount: string | null;
  commission_amount: string | null;
  unit_cost: string | null;
  margin_amount: string | null;
  /** Marge / prix HT (taux de marque). */
  margin_pct: string | null;
  /** Marge / coût (taux de marge). */
  markup_pct: string | null;
  currency: string;
  note: string | null;
  groups: GroupPriceLine[];
}

export async function previewMargin(payload: MarginPreviewRequest): Promise<MarginPreview> {
  const { data } = await api.post<MarginPreview>('/admin/products/margin-preview', payload);
  return data;
}

/** Prix saisis par groupe sur un article (group id → prix TTC). */
export async function getGroupPrices(productId: string): Promise<Record<string, string>> {
  const { data } = await api.get<{ price_group_id: string; price: string }[]>(
    `/admin/products/${productId}/group-prices`,
  );
  return Object.fromEntries(data.map((row) => [row.price_group_id, String(Number(row.price))]));
}

/** `null` retire le prix d'un groupe (la remise du groupe s'applique alors). */
export async function setGroupPrices(
  productId: string,
  prices: { price_group_id: string; price: string | null }[],
): Promise<void> {
  await api.put(`/admin/products/${productId}/group-prices`, { prices });
}
