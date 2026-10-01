import { api } from '@/boot/api';

/** Double authentification de l'administrateur connecté (`/users/me/2fa`). */
export interface TwoFactorStatus {
  enabled: boolean;
  /** Obligatoire sur ce déploiement (production par défaut). */
  required: boolean;
  recovery_codes_left: number;
}

export interface TwoFactorSetup {
  secret: string;
  otpauth_uri: string;
  /** QR code à scanner (data URI SVG). */
  qr_svg_data_uri: string;
}

export async function getTwoFactorStatus(): Promise<TwoFactorStatus> {
  const { data } = await api.get<TwoFactorStatus>('/users/me/2fa');
  return data;
}

export async function startTwoFactorSetup(): Promise<TwoFactorSetup> {
  const { data } = await api.post<TwoFactorSetup>('/users/me/2fa/setup');
  return data;
}

export async function confirmTwoFactor(code: string): Promise<string[]> {
  const { data } = await api.post<{ recovery_codes: string[] }>('/users/me/2fa/confirm', {
    code,
  });
  return data.recovery_codes;
}

export async function regenerateRecoveryCodes(code: string): Promise<string[]> {
  const { data } = await api.post<{ recovery_codes: string[] }>('/users/me/2fa/recovery-codes', {
    code,
  });
  return data.recovery_codes;
}

export async function disableTwoFactor(code: string, password: string): Promise<TwoFactorStatus> {
  const { data } = await api.post<TwoFactorStatus>('/users/me/2fa/disable', { code, password });
  return data;
}

// --- Journal d'audit -------------------------------------------------------

export interface AuditEntry {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_email: string | null;
  /** `http` (une action) ou `auth.*` (connexion, double authentification). */
  event: string;
  method: string | null;
  path: string | null;
  route: string | null;
  status_code: number | null;
  ip: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditFilters {
  event?: string | null;
  path_contains?: string | null;
  since?: string | null;
  until?: string | null;
  skip?: number;
  limit?: number;
}

export async function listAuditEntries(
  filters: AuditFilters,
): Promise<{ data: AuditEntry[]; count: number }> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== null && v !== undefined && v !== ''),
  );
  const { data } = await api.get<{ data: AuditEntry[]; count: number }>('/admin/audit-log', {
    params,
  });
  return data;
}

export async function resetUserTwoFactor(userId: string): Promise<void> {
  await api.post(`/admin/users/${userId}/2fa/reset`);
}
