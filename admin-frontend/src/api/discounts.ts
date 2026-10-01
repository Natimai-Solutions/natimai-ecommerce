import { labels } from '@/i18n/global';
import { api } from '@/boot/api';

export type DiscountType = 'coupon' | 'promotion';
export type DiscountTarget = 'product' | 'category' | 'order';

export const DISCOUNT_TARGET_LABELS: Record<DiscountTarget, string> = labels({
  order: 'api.discount_target.order',
  product: 'api.discount_target.product',
  category: 'api.discount_target.category',
});

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
  /** Code promo : s'applique aussi aux articles en promotion. */
  applies_to_promoted?: boolean;
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
  applies_to_promoted?: boolean;
}

export type DiscountUpdate = Partial<DiscountCreate> & { is_active?: boolean };

export async function listDiscounts(): Promise<Discount[]> {
  const { data } = await api.get<{ data: Discount[]; count: number }>('/discount/', {
    params: { limit: 500, include_archived: true },
  });
  return data.data ?? [];
}

export async function createDiscount(payload: DiscountCreate): Promise<Discount> {
  const { data } = await api.post<Discount>('/discount/', payload);
  return data;
}

export async function updateDiscount(id: string, payload: DiscountUpdate): Promise<Discount> {
  const { data } = await api.put<Discount>(`/discount/${id}`, payload);
  return data;
}

/** Un article trouvé par la recherche (nom, SKU, MPN) pour cibler une promotion. */
export interface ProductChoice {
  id: string;
  name: string;
  supplier_sku: string | null;
  sale_price_cached: string | null;
}

export async function searchProducts(term: string): Promise<ProductChoice[]> {
  const { data } = await api.get<{ data: ProductChoice[] }>('/product/', {
    params: { search: term, limit: 20, include_archived: true },
  });
  return data.data ?? [];
}

export async function getProductName(id: string): Promise<string | null> {
  try {
    const { data } = await api.get<ProductChoice>(`/product/${id}`);
    return data.name;
  } catch {
    return null;
  }
}
