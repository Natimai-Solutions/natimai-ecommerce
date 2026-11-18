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
