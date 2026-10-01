import { api } from '@/boot/api';

/** One public setting that has a value (`GET /system/settings`, no auth). */
export interface SystemSetting {
  key: string;
  value: string;
}

export async function getPublicSettings(): Promise<SystemSetting[]> {
  const { data } = await api.get<SystemSetting[]>('/system/settings');
  return data;
}
