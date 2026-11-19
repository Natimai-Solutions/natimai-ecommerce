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

/** L'annonce au-dessus de l'en-tête, dans la langue du visiteur (lot A3). */
export async function getAnnouncement(): Promise<HomepageSection | null> {
  const { data } = await api.get<HomepageSection | null>('/homepage/announcement');
  return data ?? null;
}

export type HomepageSeo = components['schemas']['HomepageSeoPublic'];

/** Ce que l'aperçu simule : date, public, groupe tarifaire (lot A4). */
export interface PreviewParams {
  token: string;
  at?: string | null;
  scope?: 'guest' | 'customer';
  priceGroupId?: string | null;
}

/** L'accueil tel qu'il sera (brouillons compris), avec un jeton d'aperçu
 *  de l'administration. Jamais rendu côté serveur ni mis en cache. */
export async function getHomepagePreview(params: PreviewParams): Promise<HomepageContent> {
  const { data } = await api.get<HomepageContent>('/homepage/preview', {
    headers: { 'X-Homepage-Preview': params.token },
    params: {
      ...(params.at ? { at: params.at } : {}),
      scope: params.scope ?? 'guest',
      ...(params.priceGroupId ? { price_group_id: params.priceGroupId } : {}),
    },
  });
  return data;
}

/** Lit `#apercu=…&date=…&public=…&groupe=…` : le fragment n'est jamais
 *  envoyé au serveur, le jeton ne passe ni dans les journaux ni dans l'état
 *  du rendu serveur. */
export function previewFromHash(hash: string): PreviewParams | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const token = params.get('apercu');
  if (!token) return null;
  const scope = params.get('public') === 'client' ? 'customer' : 'guest';
  return {
    token,
    at: params.get('date'),
    scope,
    priceGroupId: scope === 'customer' ? params.get('groupe') : null,
  };
}
