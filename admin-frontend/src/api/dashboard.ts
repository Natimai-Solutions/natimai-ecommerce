import { api } from '@/boot/api';

/** `GET /admin/dashboard` — files d'attente et activité récente. */
export interface DashboardTodo {
  payments_to_validate: number;
  quote_requests_open: number;
  group_upgrade_requests_pending: number;
  orders_to_process: number;
  supplier_orders_draft: number;
  product_drafts: number;
}

export interface DashboardActivity {
  currency: string;
  orders_today: number;
  orders_7d: number;
  revenue_7d: string | number;
  revenue_30d: string | number;
}

export interface DashboardDeparture {
  id: string;
  label: string;
  cutoff_at: string | null;
  departure_at: string | null;
  orders_count: number;
}

export interface AdminDashboard {
  todo: DashboardTodo;
  activity: DashboardActivity;
  next_departure: DashboardDeparture | null;
}

export async function getDashboard(): Promise<AdminDashboard> {
  const { data } = await api.get<AdminDashboard>('/admin/dashboard');
  return data;
}
