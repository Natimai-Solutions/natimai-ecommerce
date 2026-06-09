import type { components } from '@app/api-types'

type ProductPublic = components['schemas']['ProductPublic']

export function slugifyProductName(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 90)
}

export function getProductRouteByIdAndName(id: string, name: string) {
  const slug = slugifyProductName(name)
  if (!slug) return { name: 'product-detail', params: { id } }
  return { name: 'product-detail', params: { id, slug } }
}

export function getProductRoute(product: ProductPublic) {
  return getProductRouteByIdAndName(product.id, product.name)
}
