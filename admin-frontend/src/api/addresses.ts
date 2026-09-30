import { api } from '@/boot/api';

export interface AdminAddress {
  id: string;
  user_id: string;
  user_email: string | null;
  street: string;
  city: string;
  state: string | null;
  postal_code: string;
  country: string;
  type: string;
  is_validated: boolean;
}

interface Paginated<T> {
  data: T[];
  count: number;
}

export async function listAddresses(params: {
  validated?: boolean | null;
  skip?: number;
  limit?: number;
}): Promise<Paginated<AdminAddress>> {
  const query: Record<string, unknown> = {
    skip: params.skip ?? 0,
    limit: params.limit ?? 100,
  };
  if (params.validated != null) query.validated = params.validated;
  // The address router is mounted under the `/address` prefix (BaseRouter), so
  // its admin endpoints live at `/address/admin/addresses…`.
  const { data } = await api.get<Paginated<AdminAddress>>('/address/admin/addresses', {
    params: query,
  });
  return data;
}

export async function validateAddress(id: string): Promise<AdminAddress> {
  const { data } = await api.post<AdminAddress>(`/address/admin/addresses/${id}/validate`);
  return data;
}
