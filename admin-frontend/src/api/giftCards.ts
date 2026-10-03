import { labels } from '@/i18n/global';
import { api } from '@/boot/api';
import type { components } from '@app/api-types';

/** A gift card or voucher as the admin sees it (`GiftCardPublic`). */
export type GiftCard = components['schemas']['GiftCardPublic'];
export type GiftCardIssue = components['schemas']['GiftCardIssue'];
export type GiftCardKind = 'gift_card' | 'voucher';
export type GiftCardState = 'active' | 'redeemed' | 'expired' | 'cancelled';

export const GIFT_CARD_KIND_LABELS: Record<GiftCardKind, string> = labels({
  gift_card: 'api.gift_card_kind.gift_card',
  voucher: 'api.gift_card_kind.voucher',
});

export const GIFT_CARD_STATE_LABELS: Record<GiftCardState, string> = labels({
  active: 'api.gift_card_state.active',
  redeemed: 'api.gift_card_state.redeemed',
  expired: 'api.gift_card_state.expired',
  cancelled: 'api.gift_card_state.cancelled',
});

export interface GiftCardFilters {
  q?: string | undefined;
  kind?: GiftCardKind | null | undefined;
  state?: GiftCardState | null | undefined;
  skip?: number | undefined;
  limit?: number | undefined;
}

export async function listGiftCards(
  filters: GiftCardFilters = {},
): Promise<{ data: GiftCard[]; count: number }> {
  const { data } = await api.get<{ data: GiftCard[]; count: number }>('/admin/gift-cards', {
    params: filters,
  });
  return data;
}

export async function issueGiftCards(payload: GiftCardIssue): Promise<GiftCard[]> {
  const { data } = await api.post<GiftCard[]>('/admin/gift-cards', payload);
  return data;
}

export async function cancelGiftCard(id: string): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/admin/gift-cards/${id}/cancel`);
  return data;
}

export async function restoreGiftCard(id: string): Promise<GiftCard> {
  const { data } = await api.post<GiftCard>(`/admin/gift-cards/${id}/restore`);
  return data;
}
