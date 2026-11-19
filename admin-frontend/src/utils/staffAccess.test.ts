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
    expect(canOpen(support, '/quote-requests')).toBe(true);
    expect(canOpen(support, '/payments')).toBe(false);
    expect(canOpen(support, '/')).toBe(false);
    expect(homeOf(support)).toBe('/messages');
    expect(canOpen({ staff_role: 'sales' }, '/quote-requests')).toBe(true);
    expect(canOpen({ staff_role: null }, '/orders')).toBe(false);
  });

  it('opens the two-factor enrolment to every team member', () => {
    const seller = { is_superuser: false, staff_role: 'sales' };
    expect(canOpen(seller, '/security')).toBe(true);
    expect(canOpen({ staff_role: 'customer_service' }, '/security')).toBe(true);
  });

  it('never lands a team member on a switched-off screen nor on /', () => {
    const support = { is_superuser: false, staff_role: 'customer_service' };
    const messagingOff = (path: string) => path !== '/messages';
    expect(homeOf(support, messagingOff)).toBe('/orders');
    expect(homeOf({ staff_role: 'unknown' })).toBe('/security');
    expect(homeOf(support, () => false)).toBe('/security');
  });
});
