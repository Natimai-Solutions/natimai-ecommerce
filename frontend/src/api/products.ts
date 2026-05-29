import type { components } from '@app/api-types'
import { api } from 'src/boot/api'

type ProductSearchRequest = components['schemas']['ProductSearchRequest']
type ProductSearchResponse = components['schemas']['ProductSearchResponse']
type CategoryPublic = components['schemas']['CategoryPublic']
type ProductPublic = components['schemas']['ProductPublic']

export async function searchProducts(req: ProductSearchRequest): Promise<ProductSearchResponse> {
  const { data } = await api.post<ProductSearchResponse>('/product/search', req)
  return data
}

export async function getCategories(): Promise<{ data: CategoryPublic[]; count: number }> {
  const { data } = await api.get<{ data: CategoryPublic[]; count: number }>('/category')
  return data
}

export async function getProductById(productId: string): Promise<ProductPublic> {
  const { data } = await api.get<ProductPublic>(`/product/${productId}`)
  return data
}
