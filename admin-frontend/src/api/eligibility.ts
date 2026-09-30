import { api } from '@/boot/api';

export interface PaymentMethod {
  id: string;
  name: string;
  description: string | null;
  provider_code: string;
  sort_order: number;
  /** Global admin on/off switch. When false the method is hidden for everyone. */
  is_admin_active: boolean;
}

export interface PriceGroup {
  id: string;
  code: string;
  label: string;
  margin_rate_pct: string;
  default: boolean;
  requires_validation: boolean;
  /** Deposit policy: share paid at checkout (null = not offered), fee, imposed. */
  deposit_pct: string | null;
  deposit_fee_pct: string;
  deposit_fee_fixed: string;
  deposit_required: boolean;
}

export interface DepositPolicyWrite {
  deposit_pct: string | null;
  deposit_fee_pct: string;
  deposit_fee_fixed: string;
  deposit_required: boolean;
}

export async function updatePriceGroup(
  groupId: string,
  payload: Partial<DepositPolicyWrite>,
): Promise<PriceGroup> {
  const { data } = await api.patch<PriceGroup>(`/admin/price-groups/${groupId}`, payload);
  return data;
}

/** Group reference returned by the eligibility listing. */
export interface EligibleGroup {
  id: string;
  code: string;
  label: string;
}

interface PaymentMethodsResponse {
  data: PaymentMethod[];
  count: number;
}
interface PriceGroupsResponse {
  data: PriceGroup[];
  count: number;
}

export async function listPaymentMethods(): Promise<PaymentMethod[]> {
  const { data } = await api.get<PaymentMethodsResponse>('/payment_method');
  return data.data.sort((a, b) => a.sort_order - b.sort_order);
}

export async function listPriceGroups(): Promise<PriceGroup[]> {
  const { data } = await api.get<PriceGroupsResponse>('/admin/price-groups');
  return data.data;
}

/** Empty list means the method is open to every group (no restriction). */
export async function listEligibleGroups(methodId: string): Promise<EligibleGroup[]> {
  const { data } = await api.get<EligibleGroup[]>(`/admin/payment-methods/${methodId}/groups`);
  return data;
}

export async function addEligibility(methodId: string, groupId: string): Promise<void> {
  await api.post(`/admin/payment-methods/${methodId}/groups/${groupId}`);
}

export async function removeEligibility(methodId: string, groupId: string): Promise<void> {
  await api.delete(`/admin/payment-methods/${methodId}/groups/${groupId}`);
}

/** Global enable/disable of a payment method (admin). */
export async function setPaymentMethodActive(methodId: string, isActive: boolean): Promise<void> {
  await api.put(`/payment_method/${methodId}`, { is_admin_active: isActive });
}
