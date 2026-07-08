import { api } from 'src/boot/api';

export interface InventoryItem {
  product_id: string;
  product_name: string;
  is_supplier_managed: boolean;
  supplier_name: string | null;
  /** Dispo fournisseur — alimentée par la sync, lecture seule ici. */
  supplier_quantity: string;
  /** Stock physiquement détenu à l'entrepôt local. */
  local_quantity: string;
  inventory_id: string | null;
  place_id: string | null;
}

interface InventoryListResponse {
  data: InventoryItem[];
  count: number;
}

export async function listInventory(params: {
  search?: string | undefined;
  only_local?: boolean | undefined;
  skip?: number | undefined;
  limit?: number | undefined;
}): Promise<InventoryListResponse> {
  const { data } = await api.get<InventoryListResponse>('/admin/inventory', { params });
  return data;
}

export async function adjustInventory(payload: {
  product_id: string;
  place_id?: string | null;
  quantity: string;
  reason: string;
}): Promise<InventoryItem> {
  const { data } = await api.post<InventoryItem>('/admin/inventory/adjust', payload);
  return data;
}
