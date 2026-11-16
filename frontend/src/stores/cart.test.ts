import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getMyCart, mergeGuestCart, replaceMyCartItems } = vi.hoisted(() => ({
  getMyCart: vi.fn(),
  mergeGuestCart: vi.fn(),
  replaceMyCartItems: vi.fn(),
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
  replaceMyCartItems,
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

describe('the import mode of a cart line', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    replaceMyCartItems.mockReset();
  });

  const product = { id: 'p1', name: 'Écran', base_price: '11400' } as never;

  it('takes the mode and the price shown on the product page', async () => {
    const store = useCartStore();

    await store.addItem('p1', 1, product, { serviceLevel: 'economique', unitPrice: 10300 });

    expect(store.items[0]).toMatchObject({
      import_service_level: 'economique',
      unit_price: '10300.00',
    });
  });

  it('keeps the default mode and the listed price from a catalogue card', async () => {
    const store = useCartStore();

    await store.addItem('p1', 1, product);

    expect(store.items[0]).toMatchObject({ import_service_level: null, unit_price: '11400.00' });
  });

  it('reprices the whole cart on the mode chosen in the cart', async () => {
    replaceMyCartItems.mockResolvedValue({
      currency: 'XPF',
      items: [
        { product_id: 'p1', quantity: 2, unit_price: '10300', import_service_level: 'economique' },
      ],
    });
    const store = useCartStore();
    await store.addItem('p1', 2, product);

    expect(await store.setImportMode('economique')).toBe(true);

    expect(replaceMyCartItems).toHaveBeenCalledWith({
      items: [{ product_id: 'p1', quantity: 2, import_service_level: 'economique' }],
    });
    expect(store.items[0]).toMatchObject({
      import_service_level: 'economique',
      unit_price: '10300.00',
    });
    expect(store.totalAmount).toBe(20600);
  });
});
