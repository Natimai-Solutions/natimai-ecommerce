import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { searchProducts } = vi.hoisted(() => ({ searchProducts: vi.fn() }));
vi.mock('@/api/products', () => ({ searchProducts, getCategories: vi.fn() }));
vi.mock('@/i18n/global', () => ({ gt: (key: string) => key }));

import { useProductsStore } from './products';

describe('catalogue search (audit 2026-11, F2 / U2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    searchProducts.mockReset();
  });

  it('shows the results of the latest query, not of the slowest', async () => {
    let finishOld!: (value: unknown) => void;
    searchProducts
      .mockReturnValueOnce(new Promise((resolve) => (finishOld = resolve)))
      .mockResolvedValueOnce({ data: [{ id: 'new' }], count: 1 });
    const store = useProductsStore();

    const old = store.applyFilters({ q: 'ca' });
    await store.applyFilters({ q: 'casque' });
    finishOld({ data: [{ id: 'old' }], count: 1 });
    await old;

    expect(store.items.map((p) => p.id)).toEqual(['new']);
  });

  it('says the catalogue is unavailable instead of « status code 503 »', async () => {
    searchProducts.mockRejectedValueOnce(
      Object.assign(new Error('Request failed with status code 503'), {
        response: { status: 503, data: {} },
      }),
    );
    const store = useProductsStore();
    await store.search();
    expect(store.error).toBe('stores.catalogue_unavailable');
  });
});
