import { api } from 'src/boot/api';

/** A « me prévenir » alert (`StockAlertPublic`). */
export interface StockAlert {
  id: string;
  product_id: string;
  product_name: string | null;
  email: string;
  /** pending | sent | cancelled */
  status: string;
  notified_at: string | null;
  created_at: string | null;
}

/** Works signed out too: then the e-mail is required. */
export async function subscribeStockAlert(
  productId: string,
  email?: string | null,
): Promise<StockAlert> {
  const { data } = await api.post<StockAlert>('/stock-alerts', {
    product_id: productId,
    email: email || null,
  });
  return data;
}

export async function listMyStockAlerts(): Promise<StockAlert[]> {
  const { data } = await api.get<StockAlert[]>('/stock-alerts/me');
  return data;
}

export async function cancelStockAlert(alertId: string): Promise<void> {
  await api.delete(`/stock-alerts/${alertId}`);
}
