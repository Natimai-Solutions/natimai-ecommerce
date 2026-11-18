import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getFeaturedProducts, getPopularProducts, getCategories, getHomepage } = vi.hoisted(
  () => ({
    getFeaturedProducts: vi.fn(),
    getPopularProducts: vi.fn(),
    getCategories: vi.fn(),
    getHomepage: vi.fn(),
  }),
);
vi.mock('@/api/products', () => ({ getFeaturedProducts, getPopularProducts, getCategories }));
vi.mock('@/api/homepage', () => ({ getHomepage }));
vi.mock('@/boot/api', async () => {
  const { ref } = await import('vue');
  return { accessToken: ref<string | null>(null) };
});

import { accessToken } from '@/boot/api';
import { useHomeStore } from './home';

const card = (id: string, price: string) => ({ id, base_price: price });

describe('the prices of the homepage cards follow the signed-in account (§12.1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    accessToken.value = null;
    getCategories.mockResolvedValue({ data: [] });
    getHomepage.mockResolvedValue({ hero: null, banners: [] });
    getPopularProducts.mockResolvedValue([]);
    getFeaturedProducts.mockReset();
  });

  it('loads the products again once a customer is signed in, then signed out', async () => {
    getFeaturedProducts.mockResolvedValueOnce([card('p1', '45000')]);
    const home = useHomeStore();
    await home.load(); // server render: anonymous
    expect(home.featured[0]?.base_price).toBe('45000');

    accessToken.value = 'token';
    getFeaturedProducts.mockResolvedValueOnce([card('p1', '40500')]);
    await home.syncPrices();
    expect(home.featured[0]?.base_price).toBe('40500');
    expect(getHomepage).toHaveBeenCalledTimes(1);

    accessToken.value = null;
    getFeaturedProducts.mockResolvedValueOnce([card('p1', '45000')]);
    await home.syncPrices();
    expect(home.featured[0]?.base_price).toBe('45000');
  });

  it('does not fetch again when the prices are already the account’s', async () => {
    accessToken.value = 'token';
    getFeaturedProducts.mockResolvedValue([card('p1', '40500')]);
    const home = useHomeStore();
    await home.load();
    await home.syncPrices();
    expect(getFeaturedProducts).toHaveBeenCalledTimes(1);
  });
});
