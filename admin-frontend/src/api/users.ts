import { api } from '@/boot/api';

/** Un compte tel que le back-office le voit (A15) — jamais d'empreinte ni de jeton. */
export interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
  price_group_id: string | null;
  price_group_code: string | null;
  price_group_label: string | null;
  created_at: string | null;
  last_login: string | null;
  locked_until: string | null;
  /** Double authentification active (administrateurs). */
  totp_enabled?: boolean;
  /** Vrai tant que la personne n'a ni suivi le lien d'invitation ni ouvert de session. */
  invitation_pending: boolean;
  invitation_expires_at: string | null;
}

export interface AdminUsersPage {
  data: AdminUser[];
  count: number;
}

export interface AdminUserCreate {
  email: string;
  full_name?: string | null;
  phone?: string | null;
  price_group_id?: string | null;
  is_superuser?: boolean;
  send_invitation?: boolean;
}

export interface AdminUserUpdate {
  full_name?: string | null;
  phone?: string | null;
  price_group_id?: string | null;
  is_active?: boolean;
}

export interface InvitationResult {
  user: AdminUser;
  email_sent: boolean;
}

export async function listUsers(params: {
  q?: string | null;
  price_group_id?: string | null;
  is_active?: boolean | null;
  invitation_pending?: boolean | null;
  skip?: number;
  limit?: number;
}): Promise<AdminUsersPage> {
  const query: Record<string, unknown> = {
    skip: params.skip ?? 0,
    limit: params.limit ?? 50,
  };
  if (params.q) query.q = params.q;
  if (params.price_group_id) query.price_group_id = params.price_group_id;
  if (params.is_active != null) query.is_active = params.is_active;
  if (params.invitation_pending != null) query.invitation_pending = params.invitation_pending;
  const { data } = await api.get<AdminUsersPage>('/admin/users', { params: query });
  return data;
}

export async function createUser(payload: AdminUserCreate): Promise<InvitationResult> {
  const { data } = await api.post<InvitationResult>('/admin/users', payload);
  return data;
}

export async function updateUser(id: string, payload: AdminUserUpdate): Promise<AdminUser> {
  const { data } = await api.patch<AdminUser>(`/admin/users/${id}`, payload);
  return data;
}

export async function resendInvitation(id: string): Promise<InvitationResult> {
  const { data } = await api.post<InvitationResult>(`/admin/users/${id}/resend-invitation`);
  return data;
}
