import { api } from '@/boot/api';

export interface CurrencyRate {
  id: string;
  currency_code: string;
  rate_to_reference: string;
  valid_from: string;
  valid_until: string | null;
  source: 'manual' | 'auto';
  updated_by_user_id: string | null;
}

/** Which currencies the storefront offers for display (R9 / T2). */
export interface CurrencyDisplaySettings {
  reference_currency: string;
  default_display_currency: string;
  /** Currencies with a rate that the visitor cannot pick. */
  hidden_display_currencies: string[];
}

export interface CurrencyRatesResponse extends CurrencyDisplaySettings {
  data: CurrencyRate[];
  count: number;
}

export async function listCurrencyRates(): Promise<CurrencyRatesResponse> {
  const { data } = await api.get<CurrencyRatesResponse>('/admin/currency-rates');
  return data;
}

/** Offer the currency to the visitor (`true`) or hide it; the rates stay. */
export async function setCurrencyDisplay(
  code: string,
  offered: boolean,
): Promise<CurrencyDisplaySettings> {
  const { data } = await api.patch<CurrencyDisplaySettings>(
    `/admin/currency-rates/${code}/display`,
    { offered },
  );
  return data;
}

/** The currency proposed to a visitor who chose none. */
export async function setDefaultDisplayCurrency(code: string): Promise<CurrencyDisplaySettings> {
  const { data } = await api.put<CurrencyDisplaySettings>('/admin/currency-rates/display-default', {
    currency_code: code,
  });
  return data;
}

/**
 * Upsert the active rate for a currency: closes the current active rate and
 * opens a new one valid from `valid_from`. A new code adds the currency.
 */
export async function upsertCurrencyRate(
  code: string,
  payload: { rate_to_reference: string; valid_from: string },
): Promise<CurrencyRate> {
  const { data } = await api.put<CurrencyRate>(`/admin/currency-rates/${code}`, payload);
  return data;
}
