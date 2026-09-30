import { api } from '@/boot/api';

/** One whitelisted system setting (`GET /system/settings`, no auth). */
export interface SystemSetting {
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
}

export async function getPublicSettings(): Promise<SystemSetting[]> {
  const { data } = await api.get<SystemSetting[]>('/system/settings');
  return data;
}
