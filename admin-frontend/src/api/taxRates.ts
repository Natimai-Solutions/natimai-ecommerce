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
