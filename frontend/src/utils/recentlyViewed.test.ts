import { beforeEach, describe, expect, it, vi } from 'vitest';

import { RECENTLY_VIEWED_MAX, readRecentlyViewed, rememberViewed } from './recentlyViewed';

const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

describe('recently viewed products', () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => void store.set(key, value),
      },
    });
  });

  it('puts the last product first, once, and keeps twelve', () => {
    for (let n = 1; n <= RECENTLY_VIEWED_MAX + 2; n += 1) rememberViewed(id(n));
    rememberViewed(id(5));
    const ids = readRecentlyViewed();
    expect(ids[0]).toBe(id(5));
    expect(ids).toHaveLength(RECENTLY_VIEWED_MAX);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('ignores a damaged or foreign value', () => {
    window.localStorage.setItem('recently-viewed', '{"x":1}');
    expect(readRecentlyViewed()).toEqual([]);
    window.localStorage.setItem('recently-viewed', JSON.stringify(['<script>', id(1)]));
    expect(readRecentlyViewed()).toEqual([id(1)]);
  });
});
