import { api } from 'src/boot/api';

export interface DisplayRate {
  currency_code: string;
  /** 1 unit of currency_code = rate_to_reference units of the reference (XPF). */
  rate_to_reference: number;
}

export interface DisplayRatesResponse {
  reference_currency: string;
  rates: DisplayRate[];
}

export async function getDisplayRates(): Promise<DisplayRatesResponse> {
  const { data } = await api.get<DisplayRatesResponse>('/currency/display-rates');
  return data;
}
