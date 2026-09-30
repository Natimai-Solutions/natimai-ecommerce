import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type HomepageContent = components['schemas']['HomepagePublic'];
export type HomepageBlock = components['schemas']['HomepageBlockPublic'];

/** Hero et bannières publiés de l'accueil (`GET /homepage`). */
export async function getHomepage(): Promise<HomepageContent> {
  const { data } = await api.get<HomepageContent>('/homepage');
  return data;
}
