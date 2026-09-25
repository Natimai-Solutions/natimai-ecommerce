import { api } from 'src/boot/api';
import type { DepartureLike } from '@app/utils';

/** Admin view of a grouped departure (`GroupedDeparturePublic`). */
export interface Departure extends DepartureLike {
  id: string;
  estimated_delivery_at: string | null;
  departure_at: string | null;
  is_published: boolean;
  is_active: boolean;
  min_amount: string | null;
  min_units: number | null;
  recurrence_days: number | null;
  notes: string | null;
  consolidation_id: string | null;
  /** Real purchase orders placed for this departure (one per supplier). */
  supplier_orders: SupplierOrderEntry[] | null;
  created_at: string | null;
  /** Orders attached (active ones) and their total, computed by the backend. */
  orders_count: number;
  orders_total: string | number;
  /** Orders moved by a status change (PATCH response only). */
  orders_updated?: number;
}

export interface DepartureWrite {
  name: string;
  order_cutoff_at: string;
  estimated_delivery_at?: string | null;
  departure_at?: string | null;
  status?: string;
  is_published?: boolean;
  min_amount?: string | null;
  min_units?: number | null;
  recurrence_days?: number | null;
  notes?: string | null;
}

export async function listDepartures(): Promise<Departure[]> {
  const { data } = await api.get<Departure[]>('/admin/grouped-departures');
  return data;
}

export async function createDeparture(payload: DepartureWrite): Promise<Departure> {
  const { data } = await api.post<Departure>('/admin/grouped-departures', payload);
  return data;
}

export async function updateDeparture(
  id: string,
  payload: Partial<DepartureWrite>,
): Promise<Departure> {
  const { data } = await api.patch<Departure>(`/admin/grouped-departures/${id}`, payload);
  return data;
}

/** Refused (409) while orders are still attached. */
export async function deleteDeparture(id: string): Promise<void> {
  await api.delete(`/admin/grouped-departures/${id}`);
}

/** Attach, move (another departure) or detach (`null`) orders. */
export async function assignOrders(
  orderIds: string[],
  departureId: string | null,
): Promise<number> {
  const { data } = await api.post<{ updated: number }>(
    '/admin/grouped-departures/assign-orders',
    { order_ids: orderIds, departure_id: departureId },
  );
  return data.updated;
}

// --- Lot B: assisted close, supplier orders, reminders ---

export interface Shortage {
  product_id: string;
  product_name: string;
  supplier_name: string | null;
  supplier_sku: string | null;
  ordered_quantity: number;
  available_quantity: number;
  order_ids: string[];
  order_numbers: (string | null)[];
}

export interface CloseResult {
  departure_id: string;
  closed: boolean;
  orders_count: number;
  orders_total: string | number;
  threshold_reached: boolean;
  shortages: Shortage[];
  unpaid_order_ids: string[];
  next_departure_id: string | null;
}

/** Live supplier stock check + thresholds; `force` closes below a threshold. */
export async function closeDeparture(id: string, force = false): Promise<CloseResult> {
  const { data } = await api.post<CloseResult>(`/admin/grouped-departures/${id}/close`, {
    force,
  });
  return data;
}

export interface SupplierOrderEntry {
  supplier_name: string;
  order_number: string;
  ordered_at: string;
  total_amount: string | number;
  currency: string;
  notes?: string | null;
}

export async function addSupplierOrder(
  id: string,
  entry: SupplierOrderEntry,
): Promise<Departure> {
  const { data } = await api.post<Departure>(
    `/admin/grouped-departures/${id}/supplier-orders`,
    entry,
  );
  return data;
}

export async function removeSupplierOrder(id: string, index: number): Promise<Departure> {
  const { data } = await api.delete<Departure>(
    `/admin/grouped-departures/${id}/supplier-orders/${index}`,
  );
  return data;
}

export interface Reminder {
  id: string;
  grouped_departure_id: string;
  offset_days: number;
  anchor: string;
  channel: string;
  message_template: string;
  image_url: string | null;
  status: string;
  scheduled_at: string;
  sent_at: string | null;
  error: string | null;
  /** The message as it will be posted (template filled in). */
  rendered_text: string;
}

export interface ReminderWrite {
  offset_days: number;
  anchor?: string;
  channel?: string;
  message_template: string;
  image_url?: string | null;
}

export async function listReminders(departureId: string): Promise<Reminder[]> {
  const { data } = await api.get<Reminder[]>(
    `/admin/grouped-departures/${departureId}/reminders`,
  );
  return data;
}

export async function createReminder(
  departureId: string,
  payload: ReminderWrite,
): Promise<Reminder> {
  const { data } = await api.post<Reminder>(
    `/admin/grouped-departures/${departureId}/reminders`,
    payload,
  );
  return data;
}

export async function updateReminder(id: string, payload: ReminderWrite): Promise<Reminder> {
  const { data } = await api.patch<Reminder>(`/admin/grouped-departures/reminders/${id}`, payload);
  return data;
}

export async function deleteReminder(id: string): Promise<void> {
  await api.delete(`/admin/grouped-departures/reminders/${id}`);
}

/** Post the reminder now, whatever its schedule. */
export async function publishReminder(id: string): Promise<Reminder> {
  const { data } = await api.post<Reminder>(`/admin/grouped-departures/reminders/${id}/publish`);
  return data;
}
