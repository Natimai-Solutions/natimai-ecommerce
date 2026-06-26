import { describe, it, expect } from 'vitest'

import { formatXpf, parseDecimal, formatPrice, formatMoney } from '../currency'

// fr-PF groups thousands with a (narrow) non-breaking space depending on the ICU
// version — normalize all whitespace for assertions stable across Node/ICU.
const norm = (s: string) => s.replace(/\s/g, ' ')

describe('formatXpf', () => {
  it('formats integers with a thousands separator and " F" suffix', () => {
    expect(norm(formatXpf(12500))).toBe('12 500 F')
  })

  it('accepts decimal strings and rounds to the nearest franc', () => {
    expect(norm(formatXpf('12499.6'))).toBe('12 500 F')
  })

  it('formats zero', () => {
    expect(norm(formatXpf(0))).toBe('0 F')
  })

  it('returns a placeholder for non-finite input', () => {
    expect(formatXpf(Number.NaN)).toBe('— F')
    expect(formatXpf('not-a-number')).toBe('— F')
  })
})

describe('parseDecimal', () => {
  it('parses backend Decimal strings', () => {
    expect(parseDecimal('12500.00')).toBe(12500)
  })

  it('passes through numbers', () => {
    expect(parseDecimal(42)).toBe(42)
  })

  it('returns 0 for null / undefined / empty / invalid', () => {
    expect(parseDecimal(null)).toBe(0)
    expect(parseDecimal(undefined)).toBe(0)
    expect(parseDecimal('')).toBe(0)
    expect(parseDecimal('abc')).toBe(0)
  })
})

describe('formatPrice', () => {
  it('formats a backend Decimal string directly as XPF', () => {
    expect(norm(formatPrice('12500.00'))).toBe('12 500 F')
  })

  it('formats null as 0 F', () => {
    expect(norm(formatPrice(null))).toBe('0 F')
  })
})

describe('formatMoney', () => {
  it('formats XPF like formatXpf (no decimals, " F" suffix)', () => {
    expect(norm(formatMoney(12500, 'XPF'))).toBe('12 500 F')
  })

  it('formats EUR with 2 decimals and the € symbol', () => {
    const out = formatMoney(105.04, 'EUR')
    expect(out).toMatch(/105[.,]04/)
    expect(out).toContain('€')
  })

  it('formats USD with 2 decimals', () => {
    expect(formatMoney('96.2', 'USD')).toMatch(/96[.,]20/)
  })

  it('returns a currency-appropriate placeholder for non-finite input', () => {
    expect(formatMoney(Number.NaN, 'XPF')).toBe('— F')
    expect(formatMoney(Number.NaN, 'USD')).toBe('—')
  })
})
