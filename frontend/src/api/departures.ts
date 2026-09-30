import { api } from 'src/boot/api';
import type { DepartureLike } from '@app/utils';

/** Public view of a grouped departure (`GroupedDepartureSummary`, no auth). */
export interface Departure extends DepartureLike {
  id: string;
  estimated_delivery_at: string | null;
  departure_at: string | null;
}

/** The departure new orders are attached to right now, or null. */
export async function getNextDeparture(): Promise<Departure | null> {
  const { data } = await api.get<Departure | null>('/grouped-departures/next');
  return data;
}

/** A published departure (any status), e.g. the one an order is attached to. */
export async function getDeparture(id: string): Promise<Departure> {
  const { data } = await api.get<Departure>(`/grouped-departures/${id}`);
  return data;
}
