import { api } from '@/boot/api';

/**
 * Group-upgrade self-service (storefront).
 *
 * A customer can request to move to a price group that requires validation
 * (e.g. Professionnel / Revendeur). An admin then approves or rejects.
 * Backend: `/users/me/upgrade-group` (+ `/options`).
 */

/** Customer-safe price group (no internal margin). */
export interface PriceGroupOption {
  id: string;
  code: string;
  label: string;
}

export interface UpgradeGroupOptions {
  current_group: PriceGroupOption | null;
  available_groups: PriceGroupOption[];
}

export type UpgradeRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface GroupUpgradeRequest {
  id: string;
  user_id: string;
  price_group_id: string;
  status: UpgradeRequestStatus;
  business_registration_number: string;
  attestation_notes: string | null;
  admin_comment: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface GroupUpgradeRequestCreate {
  price_group_id: string;
  business_registration_number: string;
  attestation_notes?: string | null;
}

export async function getUpgradeOptions(): Promise<UpgradeGroupOptions> {
  const { data } = await api.get<UpgradeGroupOptions>('/users/me/upgrade-group/options');
  return data;
}

export async function listMyUpgradeRequests(): Promise<GroupUpgradeRequest[]> {
  const { data } = await api.get<{ data: GroupUpgradeRequest[]; count: number }>(
    '/users/me/upgrade-group',
  );
  return data.data;
}

export async function submitUpgradeRequest(
  payload: GroupUpgradeRequestCreate,
): Promise<GroupUpgradeRequest> {
  const { data } = await api.post<GroupUpgradeRequest>('/users/me/upgrade-group', payload);
  return data;
}
