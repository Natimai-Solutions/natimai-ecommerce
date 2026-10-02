import { api } from '@/boot/api';

/** One row of the general payments list (`GET /admin/payments`, A19). */
export interface PaymentRow {
  payment_id: string;
  created_at: string | null;
  provider_code: string;
  provider_reference: string | null;
  amount: number;
  currency: string;
  status: string | null;
  method_name: string | null;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  order_id: string | null;
  order_number: string | null;
  is_document: boolean;
  received_amount: number;
}

export interface PaymentListResponse {
  data: PaymentRow[];
  count: number;
  /** Every status name known to the shop, for the filter. */
  statuses: string[];
  /** Every provider code seen on a payment, for the filter. */
  provider_codes: string[];
}

export interface PaymentListFilters {
  q?: string | undefined;
  status?: string | null | undefined;
  provider_code?: string | null | undefined;
  date_from?: string | null | undefined;
  date_to?: string | null | undefined;
  skip?: number | undefined;
  limit?: number | undefined;
}

export async function listPayments(filters: PaymentListFilters = {}): Promise<PaymentListResponse> {
  const params: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    params[key] = value;
  }
  const { data } = await api.get<PaymentListResponse>('/admin/payments', { params });
  return data;
}
