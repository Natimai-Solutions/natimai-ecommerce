import { api } from 'src/boot/api';

export interface TaxRate {
  id: string;
  code: string;
  label: string;
  rate_pct: string;
  territory_code: string;
  valid_from: string;
  valid_until: string | null;
}

export interface TaxRateCreate {
  code: string;
  label: string;
  rate_pct: string;
  territory_code: string;
  valid_from: string;
  valid_until?: string | null;
}

interface TaxRatesResponse {
  data: TaxRate[];
  count: number;
}

export async function listTaxRates(params?: {
  territory_code?: string;
  valid?: boolean;
}): Promise<TaxRate[]> {
  const { data } = await api.get<TaxRatesResponse>('/admin/tax-rates', { params });
  return data.data;
}

export async function createTaxRate(payload: TaxRateCreate): Promise<TaxRate> {
  const { data } = await api.post<TaxRate>('/admin/tax-rates', payload);
  return data;
}

/** Only `label` and `valid_until` are mutable on an existing rate. */
export async function updateTaxRate(
  id: string,
  payload: { label?: string; valid_until?: string | null },
): Promise<TaxRate> {
  const { data } = await api.put<TaxRate>(`/admin/tax-rates/${id}`, payload);
  return data;
}

// --- Customs (CAF price input, resolved product → category) -----------------

export interface CategoryPublicationRow {
  category_id: string | null;
  category_name: string | null;
  default_customs_rate_pct: string | null;
  default_tax_rate_id: string | null;
  product_count: number;
  blocked_count: number;
}

export interface PublicationReport {
  enriched_count: number;
  publishable_count: number;
  blocked_customs_rate_unresolved: number;
  blocked_weight_missing: number;
  categories: CategoryPublicationRow[];
}

export async function getPublicationReport(): Promise<PublicationReport> {
  const { data } = await api.get<PublicationReport>('/admin/catalog/publication-report');
  return data;
}

/** `null` clears the rate; products then resolve nothing and stay unpublished. */
export async function setCategoryCustomsRate(
  categoryId: string,
  customsRatePct: string | null,
): Promise<void> {
  await api.put(`/admin/categories/${categoryId}/customs-rate`, {
    customs_rate_pct: customsRatePct,
  });
}
