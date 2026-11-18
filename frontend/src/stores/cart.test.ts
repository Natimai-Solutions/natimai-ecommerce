import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getMyCart, mergeGuestCart, replaceMyCartItems, replaceGuestCartItems } = vi.hoisted(() => ({
  getMyCart: vi.fn(),
  mergeGuestCart: vi.fn(),
  replaceMyCartItems: vi.fn(),
  replaceGuestCartItems: vi.fn(),
}));
vi.mock('@/api/cart', () => ({
  getMyCart,
  mergeGuestCart,
  attachGuestCartEmail: vi.fn(),
  clearGuestCart: vi.fn(),
  clearMyCart: vi.fn(),
  createGuestQuoteRequest: vi.fn(),
  reorderIntoCart: vi.fn(),
  replaceGuestCartItems,
  replaceMyCartItems,
}));
vi.mock('@/api/products', () => ({
  getProductById: vi.fn(() => Promise.reject(new Error('n/a'))),
}));
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }));
vi.mock('@/i18n/global', () => ({ gt: (key: string) => key, currentLocale: () => 'fr' }));

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

describe('a visitor cart at sign-in', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mergeGuestCart.mockReset();
    replaceGuestCartItems.mockReset();
    const memory = new Map<string, string>();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => memory.get(key) ?? null,
      setItem: (key: string, value: string) => memory.set(key, value),
      removeItem: (key: string) => memory.delete(key),
    });
    localStorage.setItem('frontend.cart.token.v1', 'g-visitor');
  });

  it('sends the lines added just before, so the merge does not drop them', async () => {
    const calls: string[] = [];
    replaceGuestCartItems.mockImplementation(() => {
      calls.push('replace');
      return Promise.resolve();
    });
    mergeGuestCart.mockImplementation(() => {
      calls.push('merge');
      return Promise.resolve({
        currency: 'XPF',
        items: [
          { product_id: 'p1', quantity: 2, unit_price: '1500' },
          { product_id: 'p-new', quantity: 1, unit_price: '900' },
        ],
      });
    });
    const store = useCartStore();
    // Added a moment ago: its debounced mirror has not run.
    store.adoptServerCart({
      currency: 'XPF',
      items: [{ product_id: 'p-new', quantity: 1, unit_price: '900' }],
    } as never);

    await store.mergeAfterLogin();

    expect(calls).toEqual(['replace', 'merge']);
    expect(replaceGuestCartItems).toHaveBeenCalledWith('g-visitor', {
      items: [{ product_id: 'p-new', quantity: 1, import_service_level: null }],
    });
    expect(store.items.map((item) => item.product_id)).toEqual(['p1', 'p-new']);
    vi.unstubAllGlobals();
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
