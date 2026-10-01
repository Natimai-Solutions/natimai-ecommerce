import { api } from '@/boot/api';

export interface DisplayRate {
  currency_code: string;
  /** Decimals of amounts in this currency (ISO 4217). */
  decimals?: number;
  /** 1 unit of currency_code = rate_to_reference units of the reference (XPF). */
  rate_to_reference: number;
}

export interface DisplayRatesResponse {
  reference_currency: string;
  reference_decimals?: number;
  rates: DisplayRate[];
}

export async function getDisplayRates(): Promise<DisplayRatesResponse> {
  const { data } = await api.get<DisplayRatesResponse>('/currency/display-rates');
  return data;
}
