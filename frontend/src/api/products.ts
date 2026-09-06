import type { components } from '@app/api-types';
import { api } from 'src/boot/api';

type ProductSearchRequest = components['schemas']['ProductSearchRequest'];
type ProductSearchResponse = components['schemas']['ProductSearchResponse'];
// `display_name` / `title` (A17) are served by the backend but the generated
// schema may lag — declare them locally. Always render `title`: it is the
// admin's storefront title, falling back to the supplier name.
export type CategoryPublic = components['schemas']['CategoryPublic'] & {
  display_name?: string | null;
  title?: string;
};
type ProductPublic = components['schemas']['ProductPublic'];
type CategorySpecFacetsResponse = components['schemas']['CategorySpecFacetsResponse'];

export interface ShippingModePricePublic {
  route_id: string;
  service_level: string | null;
  customer_label: string | null;
  freight: string;
  sale_price: string;
  eta_days: number | null;
  carbon_footprint_kg_co2e: number | null;
}

export interface ProductShippingModesResponse {
  product_id: string;
  shipping_modes: ShippingModePricePublic[];
  default_mode: string | null;
}

export async function searchProducts(req: ProductSearchRequest): Promise<ProductSearchResponse> {
  const { data } = await api.post<ProductSearchResponse>('/product/search', req);
  return data;
}

export async function getCategories(): Promise<{ data: CategoryPublic[]; count: number }> {
  const { data } = await api.get<{ data: CategoryPublic[]; count: number }>('/category');
  return data;
}

/** Available spec facets (CPU, RAM…) with value counts for a category. */
export async function getCategorySpecFacets(
  categoryId: string,
): Promise<CategorySpecFacetsResponse> {
  const { data } = await api.get<CategorySpecFacetsResponse>(
    `/product/categories/${categoryId}/spec-facets`,
  );
  return data;
}

export async function getProductById(productId: string): Promise<ProductPublic> {
  const { data } = await api.get<ProductPublic>(`/product/${productId}`);
  return data;
}

export async function getProductShippingModes(
  productId: string,
): Promise<ProductShippingModesResponse> {
  const { data } = await api.get<ProductShippingModesResponse>(
    `/product/${productId}/shipping-modes`,
  );
  return data;
}

// --- Autres offres (même produit physique chez plusieurs fournisseurs) -----

export interface ProductOfferPublic {
  product_id: string;
  name: string;
  is_current: boolean;
  supplier_name: string | null;
  supplier_label: string | null;
  is_domestic: boolean;
  pricing_mode: 'import' | 'domestic' | 'fixed';
  sale_price: string;
  supplier_quantity: string;
  in_stock: boolean;
  image_url: string | null;
}

export interface ProductOffersResponse {
  product_id: string;
  identity_key: string | null;
  offers: ProductOfferPublic[];
  cheapest_product_id: string | null;
}

/** Toutes les offres du même article (code-barres, sinon marque + réf fabricant). */
export async function getProductOffers(productId: string): Promise<ProductOffersResponse> {
  const { data } = await api.get<ProductOffersResponse>(`/product/${productId}/offers`);
  return data;
}
