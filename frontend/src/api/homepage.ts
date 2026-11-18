import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type HomepageContent = components['schemas']['HomepagePublic'];
export type HomepageSection = components['schemas']['HomepageSectionPublic'];

/** Sections de l'accueil vues par un visiteur (`GET /homepage`, rendu serveur). */
export async function getHomepage(): Promise<HomepageContent> {
  const { data } = await api.get<HomepageContent>('/homepage');
  return data;
}

/** Sections de l'accueil du client connecté : son public, ses prix. */
export async function getPersonalHomepage(): Promise<HomepageContent> {
  const { data } = await api.get<HomepageContent>('/homepage/personal');
  return data;
}
