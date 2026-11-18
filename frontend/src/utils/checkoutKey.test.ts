import { beforeEach, describe, expect, it } from 'vitest';

import { checkoutKeyFor, forgetCheckoutKey, submissionSignature } from './checkoutKey';

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

describe('checkout idempotency key', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'sessionStorage', {
      value: new MemoryStorage(),
      configurable: true,
    });
  });

  const lines = [
    { product_id: 'b', quantity: 1, import_service_level: 'rapide' },
    { product_id: 'a', quantity: 2 },
  ];

  it('is the same for a retry of the same cart, whatever the line order', () => {
    const first = checkoutKeyFor(submissionSignature(lines, null));
    const again = checkoutKeyFor(submissionSignature([...lines].reverse(), null));
    expect(again).toBe(first);
    expect(first).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });

  it('changes when the cart, the import mode or the quote changes', () => {
    const base = checkoutKeyFor(submissionSignature(lines, null));
    const more = checkoutKeyFor(
      submissionSignature([{ ...lines[0]!, quantity: 2 }, lines[1]!], null),
    );
    expect(more).not.toBe(base);
    const mode = checkoutKeyFor(
      submissionSignature([{ ...lines[0]!, import_service_level: 'economique' }, lines[1]!], null),
    );
    expect(mode).not.toBe(more);
    expect(checkoutKeyFor(submissionSignature(lines, 'q1'))).not.toBe(mode);
  });

  it('is new once the order is placed', () => {
    const signature = submissionSignature(lines, null);
    const first = checkoutKeyFor(signature);
    forgetCheckoutKey();
    expect(checkoutKeyFor(signature)).not.toBe(first);
  });
});
