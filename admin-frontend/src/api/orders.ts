import { api } from 'src/boot/api'

export interface AdminOrderListItem {
  order_id: string
  created_at: string | null
  user_id: string
  user_name: string | null
  user_email: string | null
  status: string | null
  total_amount: number
}

export interface AdminOrderLineItem {
  product_id: string
  product_name: string | null
  quantity: number
  unit_price: number
  line_total: number
}

export interface AdminOrderPaymentItem {
  payment_id: string
  provider_code: string | null
  provider_reference: string | null
  amount: number
  currency: string
  status: string | null
  created_at: string | null
}

export interface AdminOrderDetail {
  order_id: string
  created_at: string | null
  user_id: string
  user_name: string | null
  user_email: string | null
  status: string | null
  subtotal_amount: number
  shipping_fee_amount: number
  payment_fee_amount: number
  total_fees_amount: number
  total_amount: number
  shipping_address: string | null
  notes: string | null
  lines: AdminOrderLineItem[]
  payments: AdminOrderPaymentItem[]
}

export async function listOrders(): Promise<AdminOrderListItem[]> {
  const { data } = await api.get<AdminOrderListItem[]>('/admin/orders')
  return data
}

export async function getOrder(orderId: string): Promise<AdminOrderDetail> {
  const { data } = await api.get<AdminOrderDetail>(`/admin/orders/${orderId}`)
  return data
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
}

export function orderStatusLabel(name: string | null): string {
  if (!name) return '—'
  return ORDER_STATUS_LABELS[name] ?? name
}

export function orderStatusColor(name: string | null): string {
  if (name === 'Paid' || name === 'Delivered') return 'green'
  if (name === 'PaymentFailed' || name === 'Cancelled') return 'negative'
  if (name === 'Shipped' || name === 'Processing') return 'primary'
  return 'grey-7'
}
