import { api } from '@/boot/api';

export interface SystemSetting {
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
}

export async function listSystemSettings(): Promise<SystemSetting[]> {
  const { data } = await api.get<SystemSetting[]>('/admin/system-settings');
  return data;
}

export async function updateSystemSetting(
  key: string,
  payload: { value: string; description?: string | null },
): Promise<SystemSetting> {
  const { data } = await api.put<SystemSetting>(`/admin/system-settings/${key}`, payload);
  return data;
}
