import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { COMPARE_MAX, useCompareStore } from './compare';

describe('compare shortlist', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('holds at most four products and toggles them', () => {
    const store = useCompareStore();
    store.load();
    expect(store.count).toBe(0);
    for (let i = 0; i < COMPARE_MAX; i += 1) expect(store.add(`p${i}`)).toBe(true);
    expect(store.isFull).toBe(true);
    expect(store.add('p9')).toBe(false);
    expect(store.toggle('p9')).toBe(false);
    expect(store.toggle('p1')).toBe(true);
    expect(store.has('p1')).toBe(false);
    expect(store.add('p9')).toBe(true);
    expect(store.ids).toEqual(['p0', 'p2', 'p3', 'p9']);
    store.clear();
    expect(store.count).toBe(0);
  });

  it('adding twice is a no-op', () => {
    const store = useCompareStore();
    expect(store.add('a')).toBe(true);
    expect(store.add('a')).toBe(true);
    expect(store.ids).toEqual(['a']);
  });

  it('survives without a browser storage (SSR, tests)', () => {
    const store = useCompareStore();
    store.load();
    expect(store.loaded).toBe(true);
    expect(store.ids).toEqual([]);
  });
});
