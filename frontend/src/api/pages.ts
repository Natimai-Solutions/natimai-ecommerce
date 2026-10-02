import { api } from '@/boot/api';

/** A published editable page (`GET /pages/{slug}`, no auth). */
export interface ContentPage {
  slug: string;
  title: string;
  /** Written in the back-office editor; sanitise before rendering. */
  body_html: string;
  /** Language of the texts served (the request's when translated, else the default). */
  lang: string;
}

export async function getPage(slug: string): Promise<ContentPage> {
  const { data } = await api.get<ContentPage>(`/pages/${slug}`);
  return data;
}
