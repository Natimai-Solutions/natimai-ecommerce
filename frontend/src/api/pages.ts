import { api } from '@/boot/api';

/** A published editable page (`GET /pages/{slug}`, no auth). */
export interface ContentPage {
  slug: string;
  title: string;
  /** Written in the back-office editor; sanitise before rendering. */
  body_html: string;
}

export async function getPage(slug: string): Promise<ContentPage> {
  const { data } = await api.get<ContentPage>(`/pages/${slug}`);
  return data;
}
