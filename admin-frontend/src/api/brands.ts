import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type AdminBrand = components['schemas']['AdminBrand'];
export type AdminBrandList = components['schemas']['AdminBrandList'];
export type BrandWrite = components['schemas']['BrandWrite'];

/** Les fiches marque, celles à valider d'abord (lot BR). */
export async function listBrands(params: {
  q?: string | null;
  to_validate?: boolean;
}): Promise<AdminBrandList> {
  const { data } = await api.get<AdminBrandList>('/admin/brands', { params });
  return data;
}

export async function saveBrand(body: BrandWrite, id?: string): Promise<AdminBrand> {
  const { data } = id
    ? await api.put<AdminBrand>(`/admin/brands/${id}`, body)
    : await api.post<AdminBrand>('/admin/brands', body);
  return data;
}

/** `id` devient une graphie de `targetId` : produits et alias passent sur elle. */
export async function mergeBrand(id: string, targetId: string): Promise<AdminBrand> {
  const { data } = await api.post<AdminBrand>(`/admin/brands/${id}/merge`, {
    target_id: targetId,
  });
  return data;
}

export async function deleteBrand(id: string): Promise<void> {
  await api.delete(`/admin/brands/${id}`);
}

/** Rattache tout de suite les produits sans marque (le worker le fait chaque heure). */
export async function linkBrands(): Promise<number> {
  const { data } = await api.post<{ linked: number }>('/admin/brands/link');
  return data.linked;
}
