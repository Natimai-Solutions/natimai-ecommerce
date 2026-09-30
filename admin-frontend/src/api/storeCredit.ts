import { api } from 'src/boot/api';

export interface StoreCreditEntry {
  id: string;
  /** Signed: positive grant, negative use or revocation. */
  amount: string;
  currency: string;
  /** grant | use | revoke */
  kind: string;
  reason: string | null;
  order_id: string | null;
  created_at: string | null;
}

export interface StoreCreditBalance {
  user_id: string;
  currency: string;
  balance: string;
  entries: StoreCreditEntry[];
}

export const STORE_CREDIT_KIND_LABELS: Record<string, string> = {
  grant: 'Octroi',
  use: 'Utilisation',
  revoke: 'Reprise',
};

export async function getUserStoreCredit(userId: string): Promise<StoreCreditBalance> {
  const { data } = await api.get<StoreCreditBalance>(`/admin/users/${userId}/store-credit`);
  return data;
}

/** Positive amount = grant, negative = take back; the reason is required. */
export async function grantStoreCredit(
  userId: string,
  payload: { amount: string; reason: string; order_id?: string | null },
): Promise<StoreCreditBalance> {
  const { data } = await api.post<StoreCreditBalance>(
    `/admin/users/${userId}/store-credit`,
    payload,
  );
  return data;
}
