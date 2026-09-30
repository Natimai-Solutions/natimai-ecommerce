import { api } from '@/boot/api';

/** One ledger entry of the customer's store credit (`StoreCreditEntryPublic`). */
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
  grant: 'Avoir accordé',
  use: 'Utilisé sur une commande',
  revoke: 'Avoir repris',
};

export async function getMyStoreCredit(): Promise<StoreCreditBalance> {
  const { data } = await api.get<StoreCreditBalance>('/store-credit/me');
  return data;
}
