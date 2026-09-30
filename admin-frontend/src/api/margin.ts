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
}

export async function previewMargin(payload: MarginPreviewRequest): Promise<MarginPreview> {
  const { data } = await api.post<MarginPreview>('/admin/products/margin-preview', payload);
  return data;
}
