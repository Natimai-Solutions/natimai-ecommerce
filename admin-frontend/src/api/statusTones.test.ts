import { describe, expect, it, vi } from 'vitest';

// The status modules build their label tables from the app's i18n and import
// the HTTP client: neither matters for the tones.
vi.mock('@/i18n/global', () => ({ labels: () => ({}) }));
vi.mock('@/boot/api', () => ({ api: {} }));

import { orderStatusTone } from './orders';
import { quoteStatusTone } from './quoteRequests';

describe('orderStatusTone', () => {
  it('marks settled, failed and blocked orders', () => {
    expect(orderStatusTone('Paid')).toBe('ok');
    expect(orderStatusTone('DepositPaid')).toBe('ok');
    expect(orderStatusTone('Delivered')).toBe('ok');
    expect(orderStatusTone('PaymentFailed')).toBe('danger');
    expect(orderStatusTone('Cancelled')).toBe('danger');
    expect(orderStatusTone('Backordered')).toBe('warn');
    expect(orderStatusTone('PartiallyPaid')).toBe('warn');
  });

  it('leaves orders in progress neutral', () => {
    expect(orderStatusTone('InTransit')).toBe('neutral');
    expect(orderStatusTone('Pending')).toBe('neutral');
    expect(orderStatusTone(null)).toBe('neutral');
  });
});

describe('quoteStatusTone', () => {
  it('puts a quote nobody saw first', () => {
    expect(quoteStatusTone('email_failed')).toBe('danger');
    expect(quoteStatusTone('won')).toBe('ok');
    expect(quoteStatusTone('requested')).toBe('warn');
    expect(quoteStatusTone('lost')).toBe('neutral');
  });
});
