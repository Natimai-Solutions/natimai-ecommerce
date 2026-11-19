import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type HomepageBlock = components['schemas']['HomepageSectionPublic'];
export type HomepageBlockWrite = components['schemas']['HomepageBlockWrite'];

export async function listHomepageBlocks(): Promise<HomepageBlock[]> {
  const { data } = await api.get<HomepageBlock[]>('/admin/homepage-blocks');
  return data;
}

export async function createHomepageBlock(payload: HomepageBlockWrite): Promise<HomepageBlock> {
  const { data } = await api.post<HomepageBlock>('/admin/homepage-blocks', payload);
  return data;
}

export async function saveHomepageBlock(
  id: string,
  payload: HomepageBlockWrite,
): Promise<HomepageBlock> {
  const { data } = await api.put<HomepageBlock>(`/admin/homepage-blocks/${id}`, payload);
  return data;
}

export async function deleteHomepageBlock(id: string): Promise<void> {
  await api.delete(`/admin/homepage-blocks/${id}`);
}

/** The whole page order in one call (refused with 409 if the page changed). */
export async function reorderHomepageBlocks(ids: string[]): Promise<HomepageBlock[]> {
  const { data } = await api.put<HomepageBlock[]>('/admin/homepage-blocks/order', { ids });
  return data;
}

export type HomepageSeo = components['schemas']['HomepageSeoPublic'];
export type PreviewLink = components['schemas']['PreviewLink'];

/** Titre et description de l'accueil pour les moteurs (lot A4). */
export async function getHomepageSeo(): Promise<HomepageSeo> {
  const { data } = await api.get<HomepageSeo>('/admin/homepage/seo');
  return data;
}

export async function saveHomepageSeo(payload: HomepageSeo): Promise<HomepageSeo> {
  const { data } = await api.put<HomepageSeo>('/admin/homepage/seo', payload);
  return data;
}

/** Un jeton d'aperçu de 15 minutes et l'adresse de la vitrine. */
export async function createPreviewLink(): Promise<PreviewLink> {
  const { data } = await api.post<PreviewLink>('/admin/homepage/preview-token');
  return data;
}

/** L'adresse de l'aperçu : le jeton va dans le fragment (`#…`), que le
 *  navigateur n'envoie jamais au serveur. */
export function previewUrl(
  link: PreviewLink,
  options: { at?: string | null; customer?: boolean; priceGroupId?: string | null },
): string {
  const params = new URLSearchParams({ apercu: link.token });
  if (options.at) params.set('date', options.at);
  if (options.customer) {
    params.set('public', 'client');
    if (options.priceGroupId) params.set('groupe', options.priceGroupId);
  }
  return `${link.storefront_url}/#${params.toString()}`;
}
