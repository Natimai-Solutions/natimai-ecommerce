import { gt } from '@/i18n/global';
import { extractApiError } from '@/api/errors';
import { defineStore } from 'pinia';
import { ref } from 'vue';
import type { components } from '@app/api-types';
import { api } from '@/boot/api';

// `supplier_place_id` / `overridden_fields` are served by the backend (inherited
// from ProductBase) but the generated OpenAPI schema may lag — declare locally.
export type ProductPublic = components['schemas']['ProductPublic'] & {
  id: string;
  supplier_place_id?: string | null;
  overridden_fields?: string[] | null;
  /** Stock entrepôt (ligne Inventory) — servi par la liste, absent d'une création. */
  local_quantity?: string | null;
  parent_product_id?: string | null;
  /** Coût de revient HT, marge HT et taux de marque (admin uniquement). */
  unit_cost_cached?: string | null;
  margin_cached?: string | null;
  margin_pct_cached?: string | null;
  variant_options?: Record<string, string> | null;
  variants_count?: number;
};
type ProductsPublic = components['schemas']['ProductsPublic'];

/** Fields the admin product form can set (create or edit). */
export type ProductFormValues = Record<string, unknown>;

const PAGE_SIZE = 25;

export type ActiveFilter = 'all' | 'active' | 'enriched' | 'hidden' | 'inactive' | 'draft';

/** Tri serveur de la liste (vide = plus récents d'abord). */
export type ProductSort =
  | ''
  | 'price_desc'
  | 'price_asc'
  | 'cost_desc'
  | 'margin_desc'
  | 'margin_asc'
  | 'margin_pct_desc'
  | 'margin_pct_asc';

/** Une ligne du journal des prix (`ProductPriceEntryPublic`). */
export interface PriceHistoryEntry {
  id: string;
  product_id: string;
  old_price: string | null;
  new_price: string | null;
  /** Cause : product_write, nightly, currency_rate:EUR, system_setting:…, admin_inline… */
  reason: string;
  created_at: string;
}

export interface PublishResponse {
  published: number;
  already_published: number;
  missing: string[];
}

export const useProductsStore = defineStore('products', () => {
  const items = ref<ProductPublic[]>([]);
  const totalCount = ref(0);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const togglingIds = ref<Set<string>>(new Set());
  const savingOriginIds = ref<Set<string>>(new Set());

  const search = ref('');
  const activeFilter = ref<ActiveFilter>('all');
  const sort = ref<ProductSort>('');
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
          ...(sort.value ? { sort: sort.value } : {}),
        },
      });
      const list = (data.data ?? []) as ProductPublic[];
      items.value = list;
      totalCount.value = data.count ?? list.length;
    } catch (err: unknown) {
      error.value = extractApiError(err) ?? gt('common.load_failed');
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
      error.value = extractApiError(err) ?? gt('common.save_failed');
    } finally {
      togglingIds.value.delete(product.id);
      togglingIds.value = new Set(togglingIds.value);
    }
  }

  async function updateOriginPlace(product: ProductPublic, placeId: string | null) {
    savingOriginIds.value.add(product.id);
    savingOriginIds.value = new Set(savingOriginIds.value);
    try {
      await api.put(`/product/${product.id}`, { supplier_place_id: placeId });
      product.supplier_place_id = placeId;
    } catch (err: unknown) {
      error.value = extractApiError(err) ?? gt('common.save_failed');
    } finally {
      savingOriginIds.value.delete(product.id);
      savingOriginIds.value = new Set(savingOriginIds.value);
    }
  }

  /** Create a manual product via the admin endpoint, then refresh the list. */
  async function createProduct(payload: ProductFormValues): Promise<ProductPublic> {
    const { data } = await api.post<ProductPublic>('/admin/products', payload);
    await fetchPage();
    return data;
  }

  /** Update a product; edited fields are locked against the supplier sync. */
  async function updateProduct(id: string, changed: ProductFormValues): Promise<void> {
    await api.put(`/admin/products/${id}`, changed);
    await fetchPage();
  }

  /**
   * Show products on the storefront as they stand, without waiting for Icecat
   * (or take that back with `published = false`). Manual products are always
   * visible; this only matters for supplier-synced rows Icecat has not enriched.
   */
  async function publishProducts(ids: string[], published = true): Promise<number> {
    const { data } = await api.post<{ updated: number; missing: string[] }>(
      '/admin/products/publish',
      { product_ids: ids, published },
    );
    await fetchPage();
    return data.updated;
  }

  /**
   * Release one field lock. The admin value stays until the next supplier sync
   * or Icecat enrichment brings the supplier value back — nothing is restored
   * on the spot. Returns the refreshed product.
   */
  async function releaseOverride(id: string, field: string): Promise<ProductPublic> {
    const { data } = await api.delete<ProductPublic>(`/admin/products/${id}/overrides/${field}`);
    await fetchPage();
    return data;
  }

  /** Journal des prix d'un article, du plus récent au plus ancien. */
  async function priceHistory(id: string): Promise<PriceHistoryEntry[]> {
    const { data } = await api.get<PriceHistoryEntry[]>(`/admin/products/${id}/price-history`);
    return data;
  }

  /** Sortir des brouillons ; la vitrine applique ensuite ses conditions habituelles. */
  async function publishDrafts(ids: string[]): Promise<PublishResponse> {
    const { data } = await api.post<PublishResponse>('/admin/products/publish-drafts', {
      product_ids: ids,
    });
    await fetchPage();
    return data;
  }

  function setPage(n: number) {
    page.value = n;
    void fetchPage();
  }

  function applyFilters(next: {
    search?: string;
    activeFilter?: ActiveFilter;
    sort?: ProductSort;
  }) {
    if (next.search !== undefined) search.value = next.search;
    if (next.activeFilter !== undefined) activeFilter.value = next.activeFilter;
    if (next.sort !== undefined) sort.value = next.sort;
    page.value = 1;
    void fetchPage();
  }

  return {
    items,
    totalCount,
    loading,
    error,
    togglingIds,
    savingOriginIds,
    search,
    activeFilter,
    sort,
    page,
    pageSize: PAGE_SIZE,
    fetchPage,
    toggleActive,
    updateOriginPlace,
    createProduct,
    updateProduct,
    publishProducts,
    releaseOverride,
    publishDrafts,
    priceHistory,
    setPage,
    applyFilters,
  };
});
