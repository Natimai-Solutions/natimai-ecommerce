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
