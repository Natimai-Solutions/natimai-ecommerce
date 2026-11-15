import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getMyCart, mergeGuestCart } = vi.hoisted(() => ({
  getMyCart: vi.fn(),
  mergeGuestCart: vi.fn(),
}));
vi.mock('@/api/cart', () => ({
  getMyCart,
  mergeGuestCart,
  attachGuestCartEmail: vi.fn(),
  clearGuestCart: vi.fn(),
  clearMyCart: vi.fn(),
  createGuestQuoteRequest: vi.fn(),
  reorderIntoCart: vi.fn(),
  replaceGuestCartItems: vi.fn(),
  replaceMyCartItems: vi.fn(),
}));
vi.mock('@/api/products', () => ({
  getProductById: vi.fn(() => Promise.reject(new Error('n/a'))),
}));
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }));
vi.mock('@/i18n/global', () => ({ gt: (key: string) => key }));

import { useCartStore } from './cart';

const serverCart = {
  currency: 'XPF',
  items: [{ product_id: 'p1', quantity: 2, unit_price: '1500' }],
};

describe('the cart of the account at sign-in', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getMyCart.mockReset();
    mergeGuestCart.mockReset();
  });

  it('comes back after a sign-out emptied this device', async () => {
    getMyCart.mockResolvedValue(serverCart);
    const store = useCartStore();
    store.forgetLocalCart();

    await store.mergeAfterLogin();

    expect(mergeGuestCart).not.toHaveBeenCalled();
    expect(store.items.map((item) => [item.product_id, item.quantity])).toEqual([['p1', 2]]);
  });

  it('does not replace articles already on this device', async () => {
    getMyCart.mockResolvedValue(serverCart);
    const store = useCartStore();
    store.adoptServerCart({
      currency: 'XPF',
      items: [{ product_id: 'p9', quantity: 1, unit_price: '10' }],
    } as never);

    await store.mergeAfterLogin();

    expect(getMyCart).not.toHaveBeenCalled();
    expect(store.items.map((item) => item.product_id)).toEqual(['p9']);
  });

  it('merges once when two callers ask at the same time', async () => {
    getMyCart.mockResolvedValue(serverCart);
    const store = useCartStore();

    await Promise.all([store.mergeAfterLogin(), store.mergeAfterLogin()]);

    expect(getMyCart).toHaveBeenCalledTimes(1);
  });
});
