import { api } from 'src/boot/api'

export type UpgradeRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface GroupUpgradeRequest {
  id: string
  user_id: string
  price_group_id: string
  status: UpgradeRequestStatus
  business_registration_number: string
  attestation_notes: string | null
  admin_comment: string | null
  reviewed_by_id: string | null
  reviewed_at: string | null
  created_at: string
}

interface GroupUpgradeRequestsResponse {
  data: GroupUpgradeRequest[]
  count: number
}

export async function listGroupUpgradeRequests(params?: {
  pending_only?: boolean
}): Promise<GroupUpgradeRequest[]> {
  const { data } = await api.get<GroupUpgradeRequestsResponse>(
    '/admin/group-upgrade-requests',
    { params },
  )
  return data.data
}

export async function approveGroupUpgradeRequest(
  id: string,
  comment?: string | null,
): Promise<GroupUpgradeRequest> {
  const { data } = await api.post<GroupUpgradeRequest>(
    `/admin/group-upgrade-requests/${id}/approve`,
    { comment: comment ?? null },
  )
  return data
}

export async function rejectGroupUpgradeRequest(
  id: string,
  comment?: string | null,
): Promise<GroupUpgradeRequest> {
  const { data } = await api.post<GroupUpgradeRequest>(
    `/admin/group-upgrade-requests/${id}/reject`,
    { comment: comment ?? null },
  )
  return data
}
