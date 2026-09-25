import { api } from 'src/boot/api';

/** Order summary as returned by `GET /orders/me` (`OrderPublic`). */
export interface Order {
  id: string;
  user_id: string;
  order_status_id: string;
  /** Human-readable reference (CMD-2026-00042). Null for orders placed before M5. */
  order_number: string | null;
  /** Human-readable status name (Pending / AwaitingPayment / Paid / PaymentFailed…). */
  order_status_name: string | null;
  total_amount: string;
  subtotal_amount: string;
  shipping_fee_amount: string;
  payment_fee_amount: string;
  total_fees_amount: string;
  shipping_address: string | null;
  /** Last-leg delivery mode chosen at checkout: pickup | home_delivery | air_freight. */
  delivery_type: string | null;
  /** Grouped departure the order is attached to (null = classic order). */
  grouped_departure_id: string | null;
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
  /** Leg details for display, e.g. "France → Papeete (avion)". */
  from_place_name: string | null;
  to_place_name: string | null;
  mode: string | null;
  route_label: string | null;
  /** External carrier name + clickable tracking link (null when self-managed). */
  carrier_name: string | null;
  tracking_url: string | null;
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

/** Fetch a single order of the current user (resolved from the orders list). */
export async function getMyOrder(orderId: string): Promise<Order | null> {
  const orders = await listMyOrders();
  return orders.find((o) => o.id === orderId) ?? null;
}

export async function getMyOrderTracking(orderId: string): Promise<OrderTracking> {
  const { data } = await api.get<OrderTracking>(`/orders/me/${orderId}/tracking`);
  return data;
}

/** A line of the order as the customer sees it (`MyOrderLine`). */
export interface OrderLine {
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  /** Serial numbers of the units handed over (filled at reception). */
  serial_numbers: string[];
  warranty_months: number | null;
  /** Warranty end, counted from the day the goods were received. */
  warranty_until: string | null;
}

export async function getMyOrderLines(orderId: string): Promise<OrderLine[]> {
  const { data } = await api.get<OrderLine[]>(`/orders/me/${orderId}/lines`);
  return data;
}
