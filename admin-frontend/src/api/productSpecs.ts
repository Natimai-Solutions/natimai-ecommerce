import { api } from '@/boot/api';

/** One characteristic of the product form (R9 / T4): definition and current value. */
export interface SpecFormRow {
  key: string;
  label: string;
  /** `numeric` (with `unit`) or `enum` (free text, with suggestions). */
  type: string;
  unit: string | null;
  value_text: string | null;
  value_numeric: string | null;
  /** `manual`, `icecat`, or null when the product has no value yet. */
  source: string | null;
  suggestions: string[];
}

export interface SpecFormResponse {
  product_id: string | null;
  category_id: string | null;
  specs: SpecFormRow[];
}

/** The characteristics to type for a product, or for a category while creating one. */
export async function getSpecForm(params: {
  productId?: string | null;
  categoryId?: string | null;
}): Promise<SpecFormResponse> {
  const { data } = await api.get<SpecFormResponse>('/admin/products/specs-form', {
    params: {
      product_id: params.productId ?? undefined,
      category_id: params.categoryId ?? undefined,
    },
  });
  return data;
}

/** Write typed values (blank removes the value); they are never rewritten by Icecat. */
export async function setProductSpecs(
  productId: string,
  values: { key: string; value: string | null }[],
): Promise<SpecFormResponse> {
  const { data } = await api.put<SpecFormResponse>(`/admin/products/${productId}/specs`, values);
  return data;
}
