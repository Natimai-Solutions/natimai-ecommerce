import { api } from '@/boot/api';

export interface AbandonedCartLine {
  product_id: string;
  name: string;
  quantity: number;
  unit_price: string;
  line_total: string;
  image_url: string | null;
}

export interface AbandonedCart {
  cart_id: string;
  user_id: string;
  user_email: string;
  user_name: string | null;
  currency: string;
  total_amount: string;
  items_count: number;
  items: AbandonedCartLine[];
  last_activity_at: string | null;
  reminded_at: string | null;
}

export interface AbandonedCartsResponse {
  data: AbandonedCart[];
  counters: { open: number; reminded: number; recovered: number };
  reminder_delay_hours: number;
  reminder_max_age_days: number;
}

export async function listAbandonedCarts(params?: {
  skip?: number;
  limit?: number;
}): Promise<AbandonedCartsResponse> {
  const { data } = await api.get<AbandonedCartsResponse>('/admin/carts/abandoned', { params });
  return data;
}
