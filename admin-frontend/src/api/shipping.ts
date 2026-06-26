import { api } from 'src/boot/api'

export interface PendingTracking {
  tracking_id: string
  order_id: string
  route_id: string
  sequence_order: number
  status_code: string | null
  status_name: string | null
  tracking_ref: string | null
}

export interface Consolidation {
  id: string
  name: string
  consolidation_code: string
  route_id: string
  status_code: string | null
  status_name: string | null
  total_orders: number
  tracking_ref: string | null
}

export async function listPendingGrouping(): Promise<PendingTracking[]> {
  const { data } = await api.get<PendingTracking[]>('/admin/shipping/pending-grouping')
  return data
}

export async function listConsolidations(): Promise<Consolidation[]> {
  const { data } = await api.get<Consolidation[]>('/admin/shipping/consolidations')
  return data
}

export async function createConsolidation(payload: {
  route_id: string
  name: string
  notes?: string | null
}): Promise<Consolidation> {
  const { data } = await api.post<Consolidation>('/admin/shipping/consolidations', payload)
  return data
}

export async function addTrackings(
  consolidationId: string,
  trackingIds: string[],
): Promise<void> {
  await api.post(`/admin/shipping/consolidations/${consolidationId}/add-trackings`, {
    tracking_ids: trackingIds,
  })
}

export async function shipConsolidation(
  consolidationId: string,
  trackingRef: string,
): Promise<void> {
  await api.post(`/admin/shipping/consolidations/${consolidationId}/ship-all`, {
    tracking_ref: trackingRef,
  })
}

export async function shipTracking(trackingId: string, trackingRef: string): Promise<void> {
  await api.post(`/admin/shipping/trackings/${trackingId}/ship`, {
    tracking_ref: trackingRef,
  })
}

export async function deliverTracking(trackingId: string): Promise<void> {
  await api.post(`/admin/shipping/trackings/${trackingId}/deliver`)
}
