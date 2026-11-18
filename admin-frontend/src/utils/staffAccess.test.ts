import { describe, expect, it } from 'vitest';

import { canOpen, homeOf } from './staffAccess';

describe('back-office screens by role (lot ROLE)', () => {
  it('opens everything to a superuser', () => {
    expect(canOpen({ is_superuser: true }, '/system-settings')).toBe(true);
    expect(homeOf({ is_superuser: true })).toBe('/');
  });

  it('opens its screens only to a team member', () => {
    const support = { is_superuser: false, staff_role: 'customer_service' };
    expect(canOpen(support, '/messages/abc')).toBe(true);
    expect(canOpen(support, '/orders/42')).toBe(true);
    expect(canOpen(support, '/quote-requests')).toBe(false);
    expect(canOpen(support, '/')).toBe(false);
    expect(homeOf(support)).toBe('/messages');
    expect(canOpen({ staff_role: 'sales' }, '/quote-requests')).toBe(true);
    expect(canOpen({ staff_role: null }, '/orders')).toBe(false);
  });
});
