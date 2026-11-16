import type { components } from '@app/api-types';
import { api } from '@/boot/api';

export type SystemStatus = components['schemas']['SystemStatus'];
export type TaskRun = components['schemas']['TaskRunPublic'];
export type AbandonedDelivery = components['schemas']['AbandonedDelivery'];

/** Hand an abandoned delivery to the workers again. */
export async function replayAbandonedDelivery(id: string): Promise<void> {
  await api.post(`/admin/system-status/abandoned/${id}/replay`);
}

/** « État du système » : tasks, outbox, e-mails, currency rates. */
export async function getSystemStatus(): Promise<SystemStatus> {
  const { data } = await api.get<SystemStatus>('/admin/system-status');
  return data;
}
