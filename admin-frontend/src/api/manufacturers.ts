import { api } from '@/boot/api';

/** The brands already in the catalogue, one spelling each, for the product form's list. */
export async function listManufacturers(): Promise<string[]> {
  const { data } = await api.get<string[]>('/admin/products/manufacturers');
  return data;
}
