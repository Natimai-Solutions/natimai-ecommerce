import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getHomepage, getPersonalHomepage, getCategories } = vi.hoisted(() => ({
  getHomepage: vi.fn(),
  getPersonalHomepage: vi.fn(),
  getCategories: vi.fn(),
}));
vi.mock('@/api/homepage', () => ({ getHomepage, getPersonalHomepage }));
vi.mock('@/api/products', () => ({ getCategories }));
vi.mock('@/boot/api', async () => {
  const { ref } = await import('vue');
  return { accessToken: ref<string | null>(null) };
});

import { accessToken } from '@/boot/api';
import { useHomeStore } from './home';

const page = (title: string, price: string) => ({
  sections: [{ id: 's1', kind: 'featured', title, products: [{ id: 'p1', base_price: price }] }],
});

describe('the homepage of whoever is signed in (R8, §12.1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    accessToken.value = null;
    getCategories.mockResolvedValue({ data: [] });
    getHomepage.mockReset();
    getPersonalHomepage.mockReset();
  });

  it('asks for the customer’s page once signed in, and the visitor’s after signing out', async () => {
    getHomepage.mockResolvedValue(page('Coups de cœur', '45000'));
    const home = useHomeStore();
    await home.load(); // server render: anonymous
    expect(home.sections[0]?.products?.[0]?.base_price).toBe('45000');

    accessToken.value = 'token';
    getPersonalHomepage.mockResolvedValueOnce(page('Pour les pros', '40500'));
    await home.syncAudience();
    expect(home.sections[0]?.title).toBe('Pour les pros');
    expect(home.sections[0]?.products?.[0]?.base_price).toBe('40500');

    accessToken.value = null;
    await home.syncAudience();
    expect(home.sections[0]?.products?.[0]?.base_price).toBe('45000');
    expect(getHomepage).toHaveBeenCalledTimes(2);
  });

  it('asks nothing again when the page is already the customer’s', async () => {
    accessToken.value = 'token';
    getPersonalHomepage.mockResolvedValue(page('Pour les pros', '40500'));
    const home = useHomeStore();
    await home.load();
    await home.syncAudience();
    expect(getPersonalHomepage).toHaveBeenCalledTimes(1);
    expect(getHomepage).not.toHaveBeenCalled();
  });

  it('keeps the visitor’s page when the customer’s cannot be had', async () => {
    getHomepage.mockResolvedValue(page('Coups de cœur', '45000'));
    const home = useHomeStore();
    await home.load();
    accessToken.value = 'token';
    getPersonalHomepage.mockRejectedValueOnce(new Error('down'));
    await home.syncAudience();
    expect(home.sections[0]?.title).toBe('Coups de cœur');
  });
});
