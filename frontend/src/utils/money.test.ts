import { describe, expect, it } from 'vitest';

import { isPositiveAmount, orderMoney } from './money';

describe('orderMoney', () => {
  it('formate dans la devise de la commande', () => {
    expect(orderMoney('19.90', 'EUR')).toMatch(/19,90[\s\u202f]€/);
    expect(orderMoney('12500.00', 'XPF')).toMatch(/^12[\s\u202f]500\sF$/);
  });

  it('retombe sur la devise de référence', () => {
    expect(orderMoney('12500', null)).toMatch(/12[\s\u202f]500\sF/);
    expect(orderMoney('19.9', null, 'EUR')).toMatch(/19,90[\s\u202f]€/);
  });
});

describe('isPositiveAmount', () => {
  it('ne retient que les montants strictement positifs', () => {
    expect(isPositiveAmount('0.00')).toBe(false);
    expect(isPositiveAmount('150')).toBe(true);
    expect(isPositiveAmount(null)).toBe(false);
  });
});
