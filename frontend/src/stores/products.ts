import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { components } from '@app/api-types'
import { searchProducts, getCategories } from 'src/api/products'

type ProductPublic = components['schemas']['ProductPublic']
type ProductSearchRequest = components['schemas']['ProductSearchRequest']
type ProductSearchFacets = components['schemas']['ProductSearchFacets']
type CategoryPublic = components['schemas']['CategoryPublic']

const PAGE_SIZE = 24

export const useProductsStore = defineStore('products', () => {
  const items = ref<ProductPublic[]>([])
  const count = ref(0)
  const facets = ref<ProductSearchFacets | null>(null)
  const categories = ref<CategoryPublic[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const filters = ref<Omit<ProductSearchRequest, 'limit' | 'offset'>>({
    q: null,
    category_id: null,
    manufacturer: null,
    price_min: null,
    price_max: null,
    in_stock: null,
  })
  const currentPage = ref(1)

  const totalPages = computed(() => Math.ceil(count.value / PAGE_SIZE))

  async function search(overrides?: Partial<ProductSearchRequest>) {
    loading.value = true
    error.value = null
    try {
      const req: ProductSearchRequest = {
        ...filters.value,
        limit: PAGE_SIZE,
        offset: (currentPage.value - 1) * PAGE_SIZE,
        ...overrides,
      }
      const resp = await searchProducts(req)
      items.value = resp.data ?? []
      count.value = resp.count
      facets.value = resp.facets ?? null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Erreur inconnue'
    } finally {
      loading.value = false
    }
  }

  async function setPage(page: number) {
    currentPage.value = page
    await search()
  }

  async function applyFilters(newFilters: Partial<typeof filters.value>) {
    filters.value = { ...filters.value, ...newFilters }
    currentPage.value = 1
    await search()
  }

  async function loadCategories() {
    if (categories.value.length > 0) return
    try {
      const resp = await getCategories()
      categories.value = resp.data ?? []
    } catch {
      // non-critical
    }
  }

  return {
    items,
    count,
    facets,
    categories,
    loading,
    error,
    filters,
    currentPage,
    totalPages,
    search,
    setPage,
    applyFilters,
    loadCategories,
  }
})
