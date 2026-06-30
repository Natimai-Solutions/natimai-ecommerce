import { api } from 'src/boot/api';

/** Order summary as returned by `GET /orders/me` (`OrderPublic`). */
export interface Order {
  id: string;
  user_id: string;
  order_status_id: string;
  /** Human-readable status name (Pending / AwaitingPayment / Paid / PaymentFailed…). */
  order_status_name: string | null;
  total_amount: string;
  subtotal_amount: string;
  shipping_fee_amount: string;
  payment_fee_amount: string;
  total_fees_amount: string;
  shipping_address: string | null;
  notes: string | null;
  created_at: string | null;
}

/** One shipping segment of an order (`ShippingRouteTrackingPublic`). */
export interface OrderTrackingSegment {
  id: string;
  order_id: string;
  route_id: string;
  status_id: string;
  sequence_order: number;
  tracking_ref: string | null;
  estimated_delivery: string | null;
  last_status_update: string | null;
  selected_at: string | null;
  consolidation_id: string | null;
  notes: string | null;
}

/** Consolidation grouping (`ShippingRouteTrackingConsolidationPublic`). */
export interface OrderConsolidation {
  id: string;
  name: string;
  consolidation_code: string;
  status_id: string;
}

/** Aggregated tracking view (`CustomerOrderTrackingResponse`). */
export interface OrderTracking {
  order_id: string;
  trackings: OrderTrackingSegment[];
  current_route_sequence: number | null;
  /** Status code of the relevant segment, or `"unknown"`. */
  overall_status: string;
  /** e.g. `supplier_delay` | `parcel_split` | `segment_failure`. */
  exception_scenarios: string[];
  consolidations: OrderConsolidation[];
}

export async function listMyOrders(): Promise<Order[]> {
  const { data } = await api.get<Order[]>('/orders/me');
  return data;
}

export async function getMyOrderTracking(orderId: string): Promise<OrderTracking> {
  const { data } = await api.get<OrderTracking>(`/orders/me/${orderId}/tracking`);
  return data;
}
