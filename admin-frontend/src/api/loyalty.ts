import { labels } from '@/i18n/global';
import { api } from '@/boot/api';
import type { components } from '@app/api-types';

/** A customer's loyalty points: balance, value, ledger and rules. */
export type LoyaltyAccount = components['schemas']['LoyaltyAccount'];
export type LoyaltyEntry = components['schemas']['LoyaltyEntryPublic'];

export const LOYALTY_KIND_LABELS: Record<string, string> = labels({
  earn: 'api.loyalty_kind.earn',
  convert: 'api.loyalty_kind.convert',
  revoke: 'api.loyalty_kind.revoke',
  adjust: 'api.loyalty_kind.adjust',
});

export async function getUserLoyalty(userId: string): Promise<LoyaltyAccount> {
  const { data } = await api.get<LoyaltyAccount>(`/admin/users/${userId}/loyalty`);
  return data;
}

/** Positive points = bonus, negative = taken back; the reason is required. */
export async function adjustLoyalty(
  userId: string,
  payload: { points: number; reason: string; order_id?: string | null },
): Promise<LoyaltyAccount> {
  const { data } = await api.post<LoyaltyAccount>(`/admin/users/${userId}/loyalty`, payload);
  return data;
}
