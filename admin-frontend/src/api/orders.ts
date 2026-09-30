import { api } from '@/boot/api';

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
  /** full | deposit | balance — which part of the order it settles. */
  kind: string;
  created_at: string | null;
  /** Backend-computed: provider supports an in-app refund and the payment is refundable. */
  can_refund: boolean;
}

export const PAYMENT_KIND_LABELS: Record<string, string> = {
  full: 'Total',
  deposit: 'Acompte',
  balance: 'Solde',
};

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
  discount_code?: string | null;
  discount_amount?: number;
  total_amount: number;
  shipping_address: string | null;
  /** Last-leg mode chosen at checkout (home_delivery, pickup…). */
  delivery_type: string | null;
  grouped_departure_id: string | null;
  notes: string | null;
  /** Deposit order (« acompte ») : plan, amounts and where the balance stands. */
  payment_plan: string;
  deposit_amount: number;
  deposit_fee_amount: number;
  balance_amount: number;
  balance_requested_at: string | null;
  balance_paid_at: string | null;
  lines: AdminOrderLineItem[];
  payments: AdminOrderPaymentItem[];
}

/** Send (or re-send) the balance request e-mail of a deposit order. */
export async function requestBalance(
  orderId: string,
): Promise<{ order_id: string; balance_amount: number; sent: boolean }> {
  const { data } = await api.post<{ order_id: string; balance_amount: number; sent: boolean }>(
    `/admin/orders/${orderId}/request-balance`,
  );
  return data;
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
  DepositPaid: 'Acompte versé',
  PaymentFailed: 'Paiement refusé',
  PaymentReview: 'Encaissement à vérifier',
  Refunded: 'Remboursée',
  PartiallyRefunded: 'Remboursée en partie',
  // Fulfilment steps (set by hand or by the grouped departure).
  OrderedFromSupplier: 'Commandée au fournisseur',
  InTransit: 'En transit',
  AtCustoms: 'En douane',
  Received: 'Reçue, contrôle en cours',
  ReadyForPickup: 'Disponible',
  Delivered: 'Livrée',
  Backordered: 'Rupture / report',
  Cancelled: 'Annulée',
  // Legacy labels never set by the backend.
  Processing: 'En préparation',
  Shipped: 'Expédiée',
};

export function orderStatusLabel(name: string | null): string {
  if (!name) return '—';
  return ORDER_STATUS_LABELS[name] ?? name;
}

export function orderStatusColor(name: string | null): string {
  if (name === 'Paid' || name === 'Delivered' || name === 'ReadyForPickup') return 'green';
  if (name === 'DepositPaid') return 'teal';
  if (name === 'PaymentFailed' || name === 'Cancelled') return 'negative';
  if (name === 'Backordered' || name === 'PaymentReview') return 'orange';
  if (
    ['OrderedFromSupplier', 'InTransit', 'AtCustoms', 'Received', 'Shipped', 'Processing'].includes(
      name ?? '',
    )
  ) {
    return 'primary';
  }
  return 'grey-7';
}

/** Every status name the backend accepts (payment ones first, then fulfilment). */
export async function listOrderStatuses(): Promise<string[]> {
  const { data } = await api.get<string[]>('/admin/orders/statuses');
  return data;
}

export async function setOrderStatus(
  orderId: string,
  status: string,
  reason?: string,
): Promise<{ order_id: string; status: string; changed: boolean }> {
  const { data } = await api.post<{ order_id: string; status: string; changed: boolean }>(
    `/admin/orders/${orderId}/status`,
    { status, reason: reason || null },
  );
  return data;
}
