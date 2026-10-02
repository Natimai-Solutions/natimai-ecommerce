import { api } from '@/boot/api';
import type { ProductPublic } from '@/stores/products';

export interface VariantCreate {
  options: Record<string, string>;
  name?: string | null;
  supplier_sku?: string | null;
  vendor_part_number?: string | null;
  ean?: string | null;
  base_price?: string | null;
  /** Supplement over the parent's price (R9 / T6): the price is then derived. */
  price_extra?: string | null;
  cost_amount?: string | null;
  supplier_quantity?: string | null;
  image_url?: string | null;
  weight?: number | null;
}

export interface ProductVariantsAdminResponse {
  parent_id: string;
  axes: string[];
  variants: ProductPublic[];
}

/** Every variant of a product, inactive ones included. */
export async function listVariants(productId: string): Promise<ProductVariantsAdminResponse> {
  const { data } = await api.get<ProductVariantsAdminResponse>(
    `/admin/products/${productId}/variants`,
  );
  return data;
}

export async function createVariant(
  productId: string,
  payload: VariantCreate,
): Promise<ProductPublic> {
  const { data } = await api.post<ProductPublic>(`/admin/products/${productId}/variants`, payload);
  return data;
}

/** A variant is a product: edited through the admin product endpoint (fields are locked). */
export async function updateVariant(
  variantId: string,
  payload: Record<string, unknown>,
): Promise<ProductPublic> {
  const { data } = await api.put<ProductPublic>(`/admin/products/${variantId}`, payload);
  return data;
}

export async function deactivateVariant(
  productId: string,
  variantId: string,
): Promise<ProductPublic> {
  const { data } = await api.delete<ProductPublic>(
    `/admin/products/${productId}/variants/${variantId}`,
  );
  return data;
}
