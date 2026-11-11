import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getProductById } = vi.hoisted(() => ({ getProductById: vi.fn() }));
vi.mock('@/api/products', () => ({ getProductById, getProductVariants: vi.fn() }));

import { useProductDetailStore } from './productDetail';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('product page loads (audit 2026-11, F2 / U2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getProductById.mockReset();
  });

  it('keeps the latest product when an older answer arrives last', async () => {
    const a = deferred<{ id: string; has_variants: boolean }>();
    const b = deferred<{ id: string; has_variants: boolean }>();
    getProductById.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const store = useProductDetailStore();

    const loadA = store.load('A', 'fr');
    const loadB = store.load('B', 'fr');
    b.resolve({ id: 'B', has_variants: false });
    await loadB;
    a.resolve({ id: 'A', has_variants: false });
    await loadA;

    expect(store.product?.id).toBe('B');
    expect(store.loading).toBe(false);
  });

  it('shows the API message, never axios’ technical one', async () => {
    getProductById.mockRejectedValueOnce(
      Object.assign(new Error('Request failed with status code 503'), {
        response: { status: 503, data: {} },
      }),
    );
    const store = useProductDetailStore();
    await store.load('A', 'fr');
    expect(store.error).toBe('unknown');

    getProductById.mockRejectedValueOnce(
      Object.assign(new Error('Request failed with status code 409'), {
        response: { status: 409, data: { error: { code: 'x', message: 'Produit retiré' } } },
      }),
    );
    await store.load('B', 'fr');
    expect(store.error).toBe('Produit retiré');
  });
});
