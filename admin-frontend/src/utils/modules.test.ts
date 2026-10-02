import { describe, expect, it } from 'vitest';

import { ROUTE_MODULES, moduleOfPath } from './modules';

describe('moduleOfPath', () => {
  it('maps a screen and its sub-routes to their module', () => {
    expect(moduleOfPath('/suppliers')).toBe('suppliers');
    expect(moduleOfPath('/suppliers/42/edit')).toBe('suppliers');
    expect(moduleOfPath('/grouped-departures/')).toBe('grouped_departures');
  });

  it('knows no module for the always-on screens', () => {
    expect(moduleOfPath('/')).toBeNull();
    expect(moduleOfPath('/orders')).toBeNull();
    expect(moduleOfPath('/products/7')).toBeNull();
    expect(moduleOfPath('')).toBeNull();
  });

  it('covers every switchable route exactly once', () => {
    for (const [path, module] of Object.entries(ROUTE_MODULES)) {
      expect(moduleOfPath(path)).toBe(module);
    }
  });
});
