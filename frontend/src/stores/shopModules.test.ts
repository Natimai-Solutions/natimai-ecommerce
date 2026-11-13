import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { configureFormatting, formatContext } from '@app/utils';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/boot/api', () => ({ api: { get } }));

import { useShopModulesStore } from './shopModules';

describe('shop time zone in the browser (audit 2026-11)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    get.mockReset();
    configureFormatting({ timeZone: 'Pacific/Tahiti' });
  });

  it('applies the zone of the state hydrated from the server render', async () => {
    const store = useShopModulesStore();
    // As hydrated from the SSR payload: loaded, no request needed.
    store.config = { timezone: 'Europe/Paris' };
    store.loaded = true;

    await store.load();

    expect(get).not.toHaveBeenCalled();
    expect(formatContext().timeZone).toBe('Europe/Paris');
  });
});
