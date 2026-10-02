import { api } from '@/boot/api';

/** A manual link of the « Articles liés » section (R9 / T7). */
export interface ProductLink {
  id: string;
  linked_product_id: string;
  kind: string;
  position: number;
  name: string;
  vendor_part_number: string | null;
  supplier_sku: string | null;
  image_url: string | null;
  is_active: boolean;
}

export interface ProductLinkWrite {
  linked_product_id: string;
  kind: 'accessory' | 'alternative';
  position: number;
}

/** A product as the link picker lists it. */
export interface LinkCandidate {
  id: string;
  name: string;
  vendor_part_number?: string | null;
}

export async function listProductLinks(productId: string): Promise<ProductLink[]> {
  const { data } = await api.get<ProductLink[]>(`/admin/products/${productId}/links`);
  return data;
}

/** Replace every manual link of the product. */
export async function setProductLinks(
  productId: string,
  links: ProductLinkWrite[],
): Promise<ProductLink[]> {
  const { data } = await api.put<ProductLink[]>(`/admin/products/${productId}/links`, links);
  return data;
}

/** Products matching a search, for the link picker (admin listing). */
export async function searchProductsForLink(term: string): Promise<LinkCandidate[]> {
  const { data } = await api.get<{ data: LinkCandidate[] }>('/product/', {
    params: { limit: 10, search: term },
  });
  return data.data ?? [];
}
