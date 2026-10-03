import { api } from '@/boot/api';
import type { StoreCreditBalance } from '@/api/storeCredit';

/**
 * Turn a gift card or voucher code into store credit (R8 / confort). The
 * balance comes back, ready to be spent at checkout.
 */
export async function redeemGiftCard(code: string): Promise<StoreCreditBalance> {
  const { data } = await api.post<StoreCreditBalance>('/gift-cards/redeem', { code });
  return data;
}
