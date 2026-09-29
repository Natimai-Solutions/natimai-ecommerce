import { api } from 'src/boot/api';

export type DiscountType = 'coupon' | 'promotion';
export type DiscountTarget = 'product' | 'category' | 'order';

export const DISCOUNT_TARGET_LABELS: Record<DiscountTarget, string> = {
  order: 'Toute la commande',
  product: 'Un produit',
  category: 'Une catégorie',
};

/** `DiscountPublic` — the generic `/discount` CRUD (superuser). */
export interface Discount {
  id: string;
  name: string;
  description: string | null;
  discount_type: DiscountType;
  code: string | null;
  percentage: string | null;
  amount: string | null;
  min_order_amount: string | null;
  max_uses: number | null;
  max_uses_per_customer: number | null;
  current_uses: number;
  target: DiscountTarget;
  product_id: string | null;
  category_id: string | null;
  start_date: string | null;
  end_date: string | null;
  is_active: boolean;
  is_admin_active?: boolean;
  created_at: string | null;
}

export interface DiscountCreate {
  name: string;
  description?: string | null;
  discount_type: DiscountType;
  code: string | null;
  percentage: string | null;
  amount: string | null;
  min_order_amount: string | null;
  max_uses: number | null;
  max_uses_per_customer: number | null;
  target: DiscountTarget;
  product_id: string | null;
  category_id: string | null;
  start_date: string | null;
  end_date: string | null;
}

export type DiscountUpdate = Partial<DiscountCreate> & { is_active?: boolean };

export async function listDiscounts(): Promise<Discount[]> {
  const { data } = await api.get<{ data: Discount[]; count: number }>('/discount', {
    params: { limit: 500, include_archived: true },
  });
  return data.data ?? [];
}

export async function createDiscount(payload: DiscountCreate): Promise<Discount> {
  const { data } = await api.post<Discount>('/discount', payload);
  return data;
}

export async function updateDiscount(id: string, payload: DiscountUpdate): Promise<Discount> {
  const { data } = await api.put<Discount>(`/discount/${id}`, payload);
  return data;
}
