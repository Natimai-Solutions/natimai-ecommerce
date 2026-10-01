import { afterEach, describe, expect, it } from 'vitest'

import { formatMoney } from '../currency'
import { formatDate } from '../date'
import { configureFormatting, decimalsOf, setCurrencyDecimals } from '../format'

const norm = (s: string) => s.replace(/\s/g, ' ')

afterEach(() => configureFormatting({ locale: 'fr', timeZone: 'Pacific/Tahiti' }))

describe('formatting context', () => {
  it('formats money in the language of the interface', () => {
    expect(norm(formatMoney(96.2, 'EUR'))).toBe('96,20 €')
    configureFormatting({ locale: 'en' })
    expect(formatMoney(96.2, 'EUR')).toBe('€96.20')
    expect(norm(formatMoney(12500, 'XPF'))).toBe('12,500 F')
  })

  it('follows the decimals declared by the backend, else ISO 4217', () => {
    expect(decimalsOf('XPF')).toBe(0)
    expect(decimalsOf('JPY')).toBe(0)
    expect(decimalsOf('EUR')).toBe(2)
    setCurrencyDecimals({ XAU: 3 })
    expect(decimalsOf('xau')).toBe(3)
  })

  it('shows dates in the shop time zone', () => {
    // 05:00 UTC is still the previous day in Tahiti (UTC-10), not in Paris.
    expect(formatDate('2026-06-23T05:00:00Z')).toBe('22/06/2026')
    configureFormatting({ timeZone: 'Europe/Paris' })
    expect(formatDate('2026-06-23T05:00:00Z')).toBe('23/06/2026')
    configureFormatting({ locale: 'en' })
    expect(formatDate('2026-06-23T05:00:00Z')).toBe('23/06/2026')
  })
})
