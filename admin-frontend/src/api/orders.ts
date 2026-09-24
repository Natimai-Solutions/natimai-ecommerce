import { api } from 'src/boot/api';

export interface AdminOrderListItem {
  order_id: string;
  order_number: string | null;
  created_at: string | null;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  status: string | null;
  total_amount: number;
  currency: string | null;
  grouped_departure_id: string | null;
}

/** Filters shared by the list, the CSV export and the SKU summary. */
export interface OrderFilters {
  /** Orders attached to this grouped departure. */
  departure_id?: string | null;
  /** Orders with no grouped departure. */
  unassigned?: boolean;
  status?: string | null;
  date_from?: string | null;
  date_to?: string | null;
}

/** One supplier SKU aggregated over the filtered orders (= purchase-order line). */
export interface SkuSummaryRow {
  product_id: string;
  supplier_name: string | null;
  supplier_sku: string | null;
  vendor_part_number: string | null;
  product_name: string;
  quantity: number;
  orders_count: number;
  unit_cost: number | null;
  cost_currency: string | null;
  unit_weight_kg: number | null;
  total_weight_kg: number | null;
}

export interface AdminOrderLineItem {
  product_id: string;
  product_name: string | null;
  quantity: number;
  unit_price: number;
  line_total: number;
}

export interface AdminOrderPaymentItem {
  payment_id: string;
  provider_code: string | null;
  provider_reference: string | null;
  amount: number;
  currency: string;
  status: string | null;
  created_at: string | null;
  /** Backend-computed: provider supports an in-app refund and the payment is refundable. */
  can_refund: boolean;
}

export interface AdminOrderDetail {
  order_id: string;
  created_at: string | null;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  status: string | null;
  subtotal_amount: number;
  shipping_fee_amount: number;
  payment_fee_amount: number;
  total_fees_amount: number;
  total_amount: number;
  shipping_address: string | null;
  /** Last-leg mode chosen at checkout (home_delivery, pickup…). */
  delivery_type: string | null;
  grouped_departure_id: string | null;
  notes: string | null;
  lines: AdminOrderLineItem[];
  payments: AdminOrderPaymentItem[];
}

function cleanFilters(filters: OrderFilters): Record<string, string | boolean> {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== null && v !== undefined && v !== ''),
  );
}

export async function listOrders(filters: OrderFilters = {}): Promise<AdminOrderListItem[]> {
  const { data } = await api.get<AdminOrderListItem[]>('/admin/orders', {
    params: cleanFilters(filters),
  });
  return data;
}

export async function skuSummary(filters: OrderFilters = {}): Promise<SkuSummaryRow[]> {
  const { data } = await api.get<SkuSummaryRow[]>('/admin/orders/sku-summary', {
    params: cleanFilters(filters),
  });
  return data;
}

/** Download an authenticated CSV (the API needs the bearer token, so no plain link). */
async function downloadCsv(path: string, filters: OrderFilters, filename: string): Promise<void> {
  const { data } = await api.get<Blob>(path, {
    params: cleanFilters(filters),
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function downloadOrdersCsv(filters: OrderFilters = {}): Promise<void> {
  return downloadCsv('/admin/orders/export.csv', filters, 'commandes.csv');
}

export function downloadSkuSummaryCsv(filters: OrderFilters = {}): Promise<void> {
  return downloadCsv('/admin/orders/sku-summary.csv', filters, 'bon-de-commande-par-sku.csv');
}

export async function getOrder(orderId: string): Promise<AdminOrderDetail> {
  const { data } = await api.get<AdminOrderDetail>(`/admin/orders/${orderId}`);
  return data;
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  Pending: 'En attente',
  AwaitingPayment: 'En attente de paiement',
  Paid: 'Payée',
  PaymentFailed: 'Paiement refusé',
  Processing: 'En préparation',
  Shipped: 'Expédiée',
  Delivered: 'Livrée',
  Cancelled: 'Annulée',
};

export function orderStatusLabel(name: string | null): string {
  if (!name) return '—';
  return ORDER_STATUS_LABELS[name] ?? name;
}

export function orderStatusColor(name: string | null): string {
  if (name === 'Paid' || name === 'Delivered') return 'green';
  if (name === 'PaymentFailed' || name === 'Cancelled') return 'negative';
  if (name === 'Shipped' || name === 'Processing') return 'primary';
  return 'grey-7';
}
