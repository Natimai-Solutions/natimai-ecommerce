import { api } from 'src/boot/api';

/** Editable storefront page (`ContentPagePublic`). */
export interface ContentPage {
  id: string;
  slug: string;
  title: string;
  body_html: string;
  is_published: boolean;
  modify_at: string | null;
}

export interface ContentPageWrite {
  title: string;
  body_html: string;
  is_published: boolean;
}

export async function listPages(): Promise<ContentPage[]> {
  const { data } = await api.get<ContentPage[]>('/admin/pages');
  return data;
}

/** Create or replace the page `slug`. */
export async function savePage(slug: string, payload: ContentPageWrite): Promise<ContentPage> {
  const { data } = await api.put<ContentPage>(`/admin/pages/${slug}`, payload);
  return data;
}

export async function deletePage(slug: string): Promise<void> {
  await api.delete(`/admin/pages/${slug}`);
}
