import { api } from '@/boot/api';
import type { DepartureLike } from '@app/utils';

/** Public view of a grouped departure (`GroupedDepartureSummary`, no auth). */
export interface Departure extends DepartureLike {
  id: string;
  estimated_delivery_at: string | null;
  departure_at: string | null;
}

/**
 * The departure new orders are attached to right now, or null. With an
 * import mode (rapide, economique…), the one an order paid on it joins.
 */
export async function getNextDeparture(serviceLevel?: string | null): Promise<Departure | null> {
  const { data } = await api.get<Departure | null>('/grouped-departures/next', {
    params: serviceLevel ? { service_level: serviceLevel } : undefined,
  });
  return data;
}

/** A published departure (any status), e.g. the one an order is attached to. */
export async function getDeparture(id: string): Promise<Departure> {
  const { data } = await api.get<Departure>(`/grouped-departures/${id}`);
  return data;
}
