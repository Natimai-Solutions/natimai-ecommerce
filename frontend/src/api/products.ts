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

/**
 * Sellable quantity as the checkout counts it: warehouse stock plus supplier
 * stock (the latter only when the product has a supplier). Served as
 * `available_quantity` by the storefront endpoints; `supplier_quantity` is the
 * fallback for responses that do not compute it.
 */
export function sellableQuantity(product: {
  available_quantity?: string | number | null;
  supplier_quantity: string | number;
}): number {
  const raw = product.available_quantity ?? product.supplier_quantity;
  const parsed = typeof raw === 'number' ? raw : parseFloat(raw);
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : 0;
}
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

type ProductsPublic = components['schemas']['ProductsPublic'];

/** Products the admin put forward (« vedette »), in their display order. */
export async function getFeaturedProducts(limit = 8): Promise<ProductPublic[]> {
  const { data } = await api.get<ProductsPublic>('/product/featured', { params: { limit } });
  return data.data ?? [];
}

/** Most viewed products over the last `days` days. */
export async function getPopularProducts(limit = 8, days = 30): Promise<ProductPublic[]> {
  const { data } = await api.get<ProductsPublic>('/product/popular', {
    params: { limit, days },
  });
  return data.data ?? [];
}

/**
 * Count one view of a product page. Fire-and-forget: a failure must never
 * reach the customer, the counter is a marketing signal, not a feature.
 */
export async function trackProductView(productId: string): Promise<void> {
  try {
    await api.post(`/product/${productId}/view`);
  } catch {
    // ignored on purpose
  }
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
  local_quantity: string;
  available_quantity: string;
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
