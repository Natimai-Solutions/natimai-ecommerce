import { labels } from '@/i18n/global';
import { api } from '@/boot/api';
import type { components } from '@app/api-types';

export type MediaAsset = components['schemas']['MediaAssetPublic'];

/** Usage d'une image : filtre la médiathèque selon l'écran qui l'ouvre. */
export type MediaKind = 'homepage' | 'product' | 'category' | 'page' | 'other';

export const MEDIA_KIND_LABELS: Record<MediaKind, string> = labels({
  homepage: 'api.media_kind.homepage',
  product: 'api.media_kind.product',
  category: 'api.media_kind.category',
  page: 'api.media_kind.page',
  other: 'api.media_kind.other',
});

export async function listMedia(kind?: MediaKind | null): Promise<MediaAsset[]> {
  const { data } = await api.get<MediaAsset[]>('/admin/media', {
    params: kind ? { kind, limit: 120 } : { limit: 120 },
  });
  return data;
}

/** Téléverse une image : le serveur la scanne, la ré-encode en WebP et
 * renvoie ses URL (la plus grande dans `url`, toutes dans `srcset`). */
export async function uploadMedia(
  file: File,
  kind: MediaKind,
  alt?: string | null,
): Promise<MediaAsset> {
  const form = new FormData();
  form.append('file', file);
  form.append('kind', kind);
  if (alt) form.append('alt', alt);
  const { data } = await api.post<MediaAsset>('/admin/media', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function updateMedia(
  id: string,
  payload: { alt?: string | null; kind?: MediaKind },
): Promise<MediaAsset> {
  const { data } = await api.patch<MediaAsset>(`/admin/media/${id}`, payload);
  return data;
}

export async function deleteMedia(id: string): Promise<void> {
  await api.delete(`/admin/media/${id}`);
}
