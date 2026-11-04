import type { components } from '@app/api-types';

import { api } from '@/boot/api';

/** `GET /admin/dashboard` — files d'attente et activité récente. */
export type AdminDashboard = components['schemas']['AdminDashboard'];
export type DashboardTodo = components['schemas']['DashboardTodo'];

export async function getDashboard(): Promise<AdminDashboard> {
  const { data } = await api.get<AdminDashboard>('/admin/dashboard');
  return data;
}

/** `GET /admin/setup-checklist` — ce qui manque avant la première commande. */
export type SetupChecklist = components['schemas']['SetupChecklist'];
export type SetupChecklistItem = components['schemas']['SetupChecklistItem'];

export async function getSetupChecklist(): Promise<SetupChecklist> {
  const { data } = await api.get<SetupChecklist>('/admin/setup-checklist');
  return data;
}
