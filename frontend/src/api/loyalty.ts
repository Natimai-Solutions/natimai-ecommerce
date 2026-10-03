import { api } from '@/boot/api';
import type { components } from '@app/api-types';

/** The customer's loyalty points (R8 / confort): balance, value, ledger, rules. */
export type LoyaltyAccount = components['schemas']['LoyaltyAccount'];
export type LoyaltyEntry = components['schemas']['LoyaltyEntryPublic'];

export async function getMyLoyalty(): Promise<LoyaltyAccount> {
  const { data } = await api.get<LoyaltyAccount>('/loyalty/me');
  return data;
}

/** Turn points into store credit; the updated account comes back. */
export async function convertLoyaltyPoints(points: number): Promise<LoyaltyAccount> {
  const { data } = await api.post<LoyaltyAccount>('/loyalty/convert', { points });
  return data;
}
