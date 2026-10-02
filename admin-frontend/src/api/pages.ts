import { api } from '@/boot/api';

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

/** A built-in legal page a page can be started from (R9 / T1). */
export interface ContentPageTemplateSummary {
  slug: string;
  title: string;
  /** A page with this slug already exists: the template would replace its text. */
  page_exists: boolean;
}

export interface ContentPageTemplate {
  slug: string;
  title: string;
  body_html: string;
}

export async function listPageTemplates(): Promise<ContentPageTemplateSummary[]> {
  const { data } = await api.get<ContentPageTemplateSummary[]>('/admin/pages/templates');
  return data;
}

/** The template text with the seller identity already substituted. */
export async function getPageTemplate(slug: string): Promise<ContentPageTemplate> {
  const { data } = await api.get<ContentPageTemplate>(`/admin/pages/templates/${slug}`);
  return data;
}
