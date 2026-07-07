import { api } from 'src/boot/api';

export interface PendingTracking {
  tracking_id: string;
  order_id: string;
  route_id: string;
  sequence_order: number;
  status_code: string | null;
  status_name: string | null;
  tracking_ref: string | null;
  /** Dernier tronçon du parcours (livraison client) : se clôt par « Livrer ». */
  is_final_leg: boolean;
}

export interface Consolidation {
  id: string;
  name: string;
  consolidation_code: string;
  route_id: string;
  status_code: string | null;
  status_name: string | null;
  total_orders: number;
  tracking_ref: string | null;
}

export interface Carrier {
  id: string;
  name: string;
  code: string;
  tracking_url_template: string | null;
}

export async function listPendingGrouping(): Promise<PendingTracking[]> {
  const { data } = await api.get<PendingTracking[]>('/admin/shipping/pending-grouping');
  return data;
}

export async function listCarriers(): Promise<Carrier[]> {
  const { data } = await api.get<Carrier[]>('/admin/shipping/carriers');
  return data;
}

export async function listConsolidations(): Promise<Consolidation[]> {
  const { data } = await api.get<Consolidation[]>('/admin/shipping/consolidations');
  return data;
}

export async function createConsolidation(payload: {
  route_id: string;
  name: string;
  notes?: string | null;
}): Promise<Consolidation> {
  const { data } = await api.post<Consolidation>('/admin/shipping/consolidations', payload);
  return data;
}

export async function addTrackings(consolidationId: string, trackingIds: string[]): Promise<void> {
  await api.post(`/admin/shipping/consolidations/${consolidationId}/add-trackings`, {
    tracking_ids: trackingIds,
  });
}

export async function shipConsolidation(
  consolidationId: string,
  trackingRef: string | null,
  carrierId: string | null,
): Promise<void> {
  await api.post(`/admin/shipping/consolidations/${consolidationId}/ship-all`, {
    tracking_ref: trackingRef,
    carrier_id: carrierId,
  });
}

export async function shipTracking(
  trackingId: string,
  trackingRef: string | null,
  carrierId: string | null,
): Promise<void> {
  await api.post(`/admin/shipping/trackings/${trackingId}/ship`, {
    tracking_ref: trackingRef,
    carrier_id: carrierId,
  });
}

export async function deliverTracking(trackingId: string): Promise<void> {
  await api.post(`/admin/shipping/trackings/${trackingId}/deliver`);
}

export interface AdvanceResult {
  has_next: boolean;
  next_tracking_id: string | null;
  message: string;
}

/** Complete this leg and activate the next one in the order's multi-hop journey. */
export async function advanceTracking(trackingId: string): Promise<AdvanceResult> {
  const { data } = await api.post<AdvanceResult>(`/admin/shipping/trackings/${trackingId}/advance`);
  return data;
}

/** Advance every parcel of a consolidation to its next leg. */
export async function advanceConsolidation(
  consolidationId: string,
  ungroup: boolean,
): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>(
    `/admin/shipping/consolidations/${consolidationId}/advance-all`,
    { ungroup },
  );
  return data;
}

export async function deliverConsolidation(
  consolidationId: string,
): Promise<{ message: string }> {
  const { data } = await api.post<{ message: string }>(
    `/admin/shipping/consolidations/${consolidationId}/deliver-all`,
  );
  return data;
}

export async function getUngroupHint(consolidationId: string): Promise<boolean> {
  const { data } = await api.get<{ suggest_ungroup: boolean }>(
    `/admin/shipping/consolidations/${consolidationId}/ungroup-hint`,
  );
  return data.suggest_ungroup;
}

export interface JourneyLeg {
  tracking_id: string;
  sequence_order: number;
  route_name: string | null;
  from_place: string | null;
  to_place: string | null;
  mode: string | null;
  status_code: string | null;
  status_name: string | null;
  tracking_ref: string | null;
  is_current: boolean;
}

/** Ordered legs (tronçons 1..N) of an order's journey, names resolved. */
export async function getOrderJourney(orderId: string): Promise<JourneyLeg[]> {
  const { data } = await api.get<JourneyLeg[]>(`/admin/shipping/orders/${orderId}/journey`);
  return data;
}
