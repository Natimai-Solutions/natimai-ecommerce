import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { components } from '@app/api-types';
import {
  searchProducts,
  getCategories,
  getCategorySpecFacets,
  type CategoryPublic,
} from '@/api/products';
import { gt } from '@/i18n/global';
import { apiErrorMessage } from '@/utils/errors';

type ProductPublic = components['schemas']['ProductPublic'];
type ProductSearchRequest = components['schemas']['ProductSearchRequest'];
type ProductSearchFacets = components['schemas']['ProductSearchFacets'];
type SpecFacet = components['schemas']['SpecFacet'];

const PAGE_SIZE = 24;

export const useProductsStore = defineStore('products', () => {
  const items = ref<ProductPublic[]>([]);
  const count = ref(0);
  const facets = ref<ProductSearchFacets | null>(null);
  /** Nothing had the words searched: the results only resemble them. */
  const approximate = ref(false);
  const categories = ref<CategoryPublic[]>([]);
  const specFacets = ref<SpecFacet[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const filters = ref<Omit<ProductSearchRequest, 'limit' | 'offset'>>({
    q: null,
    category_id: null,
    manufacturer: null,
    price_min: null,
    price_max: null,
    in_stock: null,
    stock: null,
    condition: null,
    specs: {},
    // Défaut du backend : un même article vendu par plusieurs fournisseurs
    // n'apparaît qu'une fois, à sa meilleure offre.
    group_offers: true,
    sort: 'relevance',
  });
  const currentPage = ref(1);

  const totalPages = computed(() => Math.ceil(count.value / PAGE_SIZE));

  /** Only the latest search writes: typing fast, an older answer arriving
   *  last showed results for a query no longer in the box (F2). */
  let latestSearch = 0;

  async function search(overrides?: Partial<ProductSearchRequest>) {
    const call = ++latestSearch;
    loading.value = true;
    error.value = null;
    try {
      const req: ProductSearchRequest = {
        ...filters.value,
        limit: PAGE_SIZE,
        offset: (currentPage.value - 1) * PAGE_SIZE,
        ...overrides,
      };
      const resp = await searchProducts(req);
      if (call !== latestSearch) return;
      items.value = resp.data ?? [];
      count.value = resp.count;
      facets.value = resp.facets ?? null;
      approximate.value = resp.approximate ?? false;
    } catch (e) {
      if (call !== latestSearch) return;
      // Never axios' English « Request failed with status code 503 » (U2).
      error.value = apiErrorMessage(e) ?? gt('stores.catalogue_unavailable');
    } finally {
      if (call === latestSearch) loading.value = false;
    }
  }

  async function setPage(page: number) {
    currentPage.value = page;
    await search();
  }

  async function applyFilters(newFilters: Partial<typeof filters.value>) {
    filters.value = { ...filters.value, ...newFilters };
    currentPage.value = 1;
    await search();
  }

  async function loadCategories(options: { force?: boolean } = {}) {
    if (categories.value.length > 0 && !options.force) return;
    try {
      const resp = await getCategories();
      // Merged (A12) or switched-off categories stay in base for the supplier
      // sync but have no place in the storefront filter.
      categories.value = (resp.data ?? []).filter(
        (c) => c.is_active !== false && c.is_admin_active !== false && !c.merged_into_id,
      );
    } catch {
      // non-critical
    }
  }

  /** Load the spec facets (CPU, RAM…) for a category, or clear them when null. */
  async function loadSpecFacets(categoryId: string | null) {
    if (!categoryId) {
      specFacets.value = [];
      return;
    }
    try {
      const resp = await getCategorySpecFacets(categoryId);
      specFacets.value = resp.specs ?? [];
    } catch {
      specFacets.value = [];
    }
  }

  return {
    items,
    count,
    facets,
    approximate,
    categories,
    specFacets,
    loading,
    error,
    filters,
    currentPage,
    totalPages,
    search,
    setPage,
    applyFilters,
    loadCategories,
    loadSpecFacets,
  };
});
