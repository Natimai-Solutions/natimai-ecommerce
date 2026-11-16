import type { components } from '@app/api-types';
import { api } from '@/boot/api';

export type SystemStatus = components['schemas']['SystemStatus'];
export type TaskRun = components['schemas']['TaskRunPublic'];

/** « État du système » : tasks, outbox, e-mails, currency rates. */
export async function getSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>('/admin/system-status');
  return data;
}
