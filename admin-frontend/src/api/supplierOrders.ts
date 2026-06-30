import { api } from 'src/boot/api';

export type SupplierOrderStatus = 'pending' | 'submitted' | 'error' | 'skipped';

export interface SupplierOrder {
  id: string;
  supplier_name: string;
  local_order_id: string;
  customer_order_number: string;
  supplier_order_number: string | null;
  status: SupplierOrderStatus;
  supplier_status_label: string | null;
  error_message: string | null;
  attempts: number;
  estimated_delivery: string | null;
  created_at: string;
  updated_at: string;
}

interface SupplierOrdersResponse {
  data: SupplierOrder[];
  count: number;
}

export async function listSupplierOrders(params?: {
  status?: SupplierOrderStatus;
  supplier_name?: string;
  skip?: number;
  limit?: number;
}): Promise<SupplierOrdersResponse> {
  const { data } = await api.get<SupplierOrdersResponse>('/admin/supplier-orders', {
    params,
  });
  return data;
}

export async function retrySupplierOrder(id: string): Promise<SupplierOrder> {
  const { data } = await api.post<SupplierOrder>(`/admin/supplier-orders/${id}/retry`);
  return data;
}
