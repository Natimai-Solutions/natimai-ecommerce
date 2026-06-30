import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';
import { api } from 'src/boot/api';

type ProductPublic = components['schemas']['ProductPublic'] & { id: string };
type ProductsPublic = components['schemas']['ProductsPublic'];

const PAGE_SIZE = 25;

export type ActiveFilter = 'all' | 'active' | 'enriched' | 'inactive';

export const useProductsStore = defineStore('products', () => {
  const items = ref<ProductPublic[]>([]);
  const totalCount = ref(0);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const togglingIds = ref<Set<string>>(new Set());

  const search = ref('');
  const activeFilter = ref<ActiveFilter>('all');
  const page = ref(1);

  async function fetchPage() {
    loading.value = true;
    error.value = null;
    try {
      const term = search.value.trim();
      const { data } = await api.get<ProductsPublic>('/product/', {
        params: {
          skip: (page.value - 1) * PAGE_SIZE,
          limit: PAGE_SIZE,
          include_archived: true,
          ...(activeFilter.value !== 'all' ? { status: activeFilter.value } : {}),
          ...(term ? { search: term } : {}),
        },
      });
      const list = (data.data ?? []) as ProductPublic[];
      items.value = list;
      totalCount.value = data.count ?? list.length;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Erreur de chargement';
    } finally {
      loading.value = false;
    }
  }

  async function toggleActive(product: ProductPublic) {
    const next = !product.is_admin_active;
    togglingIds.value.add(product.id);
    try {
      await api.put(`/product/${product.id}`, { is_admin_active: next });
      product.is_admin_active = next;
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : 'Échec de mise à jour';
    } finally {
      togglingIds.value.delete(product.id);
      togglingIds.value = new Set(togglingIds.value);
    }
  }

  function setPage(n: number) {
    page.value = n;
    void fetchPage();
  }

  function applyFilters(next: { search?: string; activeFilter?: ActiveFilter }) {
    if (next.search !== undefined) search.value = next.search;
    if (next.activeFilter !== undefined) activeFilter.value = next.activeFilter;
    page.value = 1;
    void fetchPage();
  }

  return {
    items,
    totalCount,
    loading,
    error,
    togglingIds,
    search,
    activeFilter,
    page,
    pageSize: PAGE_SIZE,
    fetchPage,
    toggleActive,
    setPage,
    applyFilters,
  };
});
