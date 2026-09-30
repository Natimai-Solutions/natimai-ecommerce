import { api } from '@/boot/api';

/** A payment method as the admin manages it (GET /admin/payment-methods). */
export interface PaymentMethod {
  id: string;
  name: string;
  description: string | null;
  /** Its type (payzen, paypal, manual_cash…): fixed once created. */
  provider_code: string;
  type_label: string;
  /** card | wallet | manual | document */
  family: string;
  /** The customer receives instructions (manual and document types). */
  supports_instructions: boolean;
  fee: string;
  /** Maximum order amount (null = no cap). */
  max_amount: string | null;
  sort_order: number;
  /** Global admin on/off switch. When false the method is hidden for everyone. */
  is_admin_active: boolean;
  /** Whether the method can pay a deposit (the balance stays open to all). */
  deposit_allowed: boolean;
  /** Its own instructions (null = those of its type). */
  instructions: string | null;
  /** Payments made with it: a used method cannot be deleted. */
  payments_count: number;
}

/** A type a method can be created on (behaviour fixed in the code). */
export interface PaymentMethodType {
  code: string;
  label: string;
  family: string;
  supports_instructions: boolean;
  /** What the customer receives when the method has no text of its own. */
  fallback_instructions: string | null;
}

export interface PaymentMethodWrite {
  name?: string;
  description?: string | null;
  fee?: string;
  max_amount?: string | null;
  sort_order?: number;
  is_admin_active?: boolean;
  deposit_allowed?: boolean;
  instructions?: string | null;
}

export async function listPaymentMethodTypes(): Promise<PaymentMethodType[]> {
  const { data } = await api.get<PaymentMethodType[]>('/admin/payment-methods/types');
  return data;
}

export async function createPaymentMethod(
  payload: PaymentMethodWrite & { provider_code: string; name: string },
): Promise<PaymentMethod> {
  const { data } = await api.post<PaymentMethod>('/admin/payment-methods', payload);
  return data;
}

export async function updatePaymentMethod(
  methodId: string,
  payload: PaymentMethodWrite,
): Promise<PaymentMethod> {
  const { data } = await api.patch<PaymentMethod>(`/admin/payment-methods/${methodId}`, payload);
  return data;
}

/** Refused (409) once a payment used the method: switch it off instead. */
export async function deletePaymentMethod(methodId: string): Promise<void> {
  await api.delete(`/admin/payment-methods/${methodId}`);
}

export interface PriceGroup {
  id: string;
  code: string;
  label: string;
  margin_rate_pct: string;
  /** Remise du groupe en % du prix de référence (0 pour le groupe par défaut). */
  discount_pct: string;
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
  payload: Partial<DepositPolicyWrite> & { discount_pct?: string; margin_rate_pct?: string },
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

interface PriceGroupsResponse {
  data: PriceGroup[];
  count: number;
}

/** Every method, switched on or off, in checkout order. */
export async function listPaymentMethods(): Promise<PaymentMethod[]> {
  const { data } = await api.get<PaymentMethod[]>('/admin/payment-methods');
  return data;
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
  await updatePaymentMethod(methodId, { is_admin_active: isActive });
}

/** Allow or exclude a payment method for deposits (admin). */
export async function setPaymentMethodDepositAllowed(
  methodId: string,
  allowed: boolean,
): Promise<void> {
  await updatePaymentMethod(methodId, { deposit_allowed: allowed });
}

/** A card / wallet provider (PayZen, PayPal, Stripe) and its switch. */
export interface PaymentProvider {
  code: string;
  label: string;
  enabled: boolean;
  credentials_present: boolean;
  implemented: boolean;
  /** Switched on, implemented and with credentials: takes new payments. */
  available: boolean;
}

export async function listPaymentProviders(): Promise<PaymentProvider[]> {
  const { data } = await api.get<PaymentProvider[]>('/admin/payment-providers');
  return data;
}

export async function setPaymentProviderEnabled(
  code: string,
  enabled: boolean,
): Promise<PaymentProvider[]> {
  const { data } = await api.put<PaymentProvider[]>(`/admin/payment-providers/${code}`, {
    enabled,
  });
  return data;
}
