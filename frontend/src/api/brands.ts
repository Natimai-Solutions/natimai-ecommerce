import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type BrandPage = components['schemas']['BrandPagePublic'];

/** Une marque validée par son adresse (`/marque/<slug>`). */
export async function getBrandPage(slug: string): Promise<BrandPage> {
  const { data } = await api.get<BrandPage>(`/brands/page/${encodeURIComponent(slug)}`);
  return data;
}

/** Les marques à logo qui ont des produits en vente (bande de l'accueil). */
export async function getBrandShowcase(limit = 24): Promise<BrandPage[]> {
  const { data } = await api.get<BrandPage[]>('/brands/showcase', { params: { limit } });
  return data;
}
