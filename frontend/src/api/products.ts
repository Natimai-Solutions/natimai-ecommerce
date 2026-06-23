import type { components } from '@app/api-types'
import { api } from 'src/boot/api'

type ProductSearchRequest = components['schemas']['ProductSearchRequest']
type ProductSearchResponse = components['schemas']['ProductSearchResponse']
type CategoryPublic = components['schemas']['CategoryPublic']
type ProductPublic = components['schemas']['ProductPublic']
type CategorySpecFacetsResponse = components['schemas']['CategorySpecFacetsResponse']

export interface ShippingModePricePublic {
  route_id: string
  service_level: string | null
  customer_label: string | null
  freight: string
  sale_price: string
  eta_days: number | null
  carbon_footprint_kg_co2e: number | null
}

export interface ProductShippingModesResponse {
  product_id: string
  shipping_modes: ShippingModePricePublic[]
  default_mode: string | null
}

export async function searchProducts(req: ProductSearchRequest): Promise<ProductSearchResponse> {
  const { data } = await api.post<ProductSearchResponse>('/product/search', req)
  return data
}

export async function getCategories(): Promise<{ data: CategoryPublic[]; count: number }> {
  const { data } = await api.get<{ data: CategoryPublic[]; count: number }>('/category')
  return data
}

/** Available spec facets (CPU, RAM…) with value counts for a category. */
export async function getCategorySpecFacets(
  categoryId: string,
): Promise<CategorySpecFacetsResponse> {
  const { data } = await api.get<CategorySpecFacetsResponse>(
    `/product/categories/${categoryId}/spec-facets`,
  )
  return data
}

export async function getProductById(productId: string): Promise<ProductPublic> {
  const { data } = await api.get<ProductPublic>(`/product/${productId}`)
  return data
}

export async function getProductShippingModes(
  productId: string,
): Promise<ProductShippingModesResponse> {
  const { data } = await api.get<ProductShippingModesResponse>(
    `/product/${productId}/shipping-modes`,
  )
  return data
}
