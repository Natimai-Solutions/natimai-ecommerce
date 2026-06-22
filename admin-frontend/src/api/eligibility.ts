import { api } from 'src/boot/api'

export interface PaymentMethod {
  id: string
  name: string
  description: string | null
  provider_code: string
  sort_order: number
}

export interface PriceGroup {
  id: string
  code: string
  label: string
  margin_rate_pct: string
  default: boolean
  requires_validation: boolean
}

/** Group reference returned by the eligibility listing. */
export interface EligibleGroup {
  id: string
  code: string
  label: string
}

interface PaymentMethodsResponse {
  data: PaymentMethod[]
  count: number
}
interface PriceGroupsResponse {
  data: PriceGroup[]
  count: number
}

export async function listPaymentMethods(): Promise<PaymentMethod[]> {
  const { data } = await api.get<PaymentMethodsResponse>('/payment_method')
  return data.data.sort((a, b) => a.sort_order - b.sort_order)
}

export async function listPriceGroups(): Promise<PriceGroup[]> {
  const { data } = await api.get<PriceGroupsResponse>('/admin/price-groups')
  return data.data
}

/** Empty list means the method is open to every group (no restriction). */
export async function listEligibleGroups(methodId: string): Promise<EligibleGroup[]> {
  const { data } = await api.get<EligibleGroup[]>(
    `/admin/payment-methods/${methodId}/groups`,
  )
  return data
}

export async function addEligibility(methodId: string, groupId: string): Promise<void> {
  await api.post(`/admin/payment-methods/${methodId}/groups/${groupId}`)
}

export async function removeEligibility(
  methodId: string,
  groupId: string,
): Promise<void> {
  await api.delete(`/admin/payment-methods/${methodId}/groups/${groupId}`)
}
