import { api } from 'src/boot/api'

export interface CurrencyRate {
  id: string
  currency_code: string
  rate_to_reference: string
  valid_from: string
  valid_until: string | null
  source: 'manual' | 'auto'
  updated_by_user_id: string | null
}

interface CurrencyRatesResponse {
  data: CurrencyRate[]
  count: number
}

export async function listCurrencyRates(): Promise<CurrencyRate[]> {
  const { data } = await api.get<CurrencyRatesResponse>('/admin/currency-rates')
  return data.data
}

/**
 * Upsert the active rate for a currency: closes the current active rate and
 * opens a new one valid from `valid_from`.
 */
export async function upsertCurrencyRate(
  code: string,
  payload: { rate_to_reference: string; valid_from: string },
): Promise<CurrencyRate> {
  const { data } = await api.put<CurrencyRate>(`/admin/currency-rates/${code}`, payload)
  return data
}
