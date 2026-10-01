/**
 * Money formatting.
 *
 * `formatMoney(amount, currency)` is the one to use: it follows the language
 * of the interface (`configureFormatting`) and the decimals of the currency
 * (declared by the backend, else ISO 4217). XPF has no decimals and keeps its
 * conventional " F" suffix in every language.
 *
 * `formatXpf` / `formatPrice` remain for amounts that are XPF by nature.
 */

import { decimalsOf, intlLocale } from './format'

/**
 * Format a number or string amount as XPF.
 *
 * @example
 *   formatXpf(12500)    // "12 500 F"
 *   formatXpf("12500")  // "12 500 F"
 *   formatXpf(0)        // "0 F"
 */
export function formatXpf(amount: number | string): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  if (!isFinite(n)) return '— F'

  return (
    new Intl.NumberFormat(intlLocale(), {
      style: 'decimal',
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    }).format(Math.round(n)) + ' F'
  )
}

/**
 * Parse a backend Decimal string to a JS number.
 * Backend sends Decimal fields as strings (e.g. "12500.00").
 */
export function parseDecimal(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const n = typeof value === 'number' ? value : parseFloat(String(value))
  return isFinite(n) ? n : 0
}

/**
 * Format a price from a backend Decimal string directly as XPF.
 */
export function formatPrice(decimalStr: string | number | null | undefined): string {
  return formatXpf(parseDecimal(decimalStr))
}

/**
 * Format an amount in a currency, in the language of the interface.
 *
 * @example (French)
 *   formatMoney(12500, 'XPF')  // "12 500 F"
 *   formatMoney(105.04, 'USD') // "105,04 $US"
 *   formatMoney(96.2, 'EUR')   // "96,20 €"
 * @example (English)
 *   formatMoney(96.2, 'EUR')   // "€96.20"
 */
export function formatMoney(amount: number | string, currency: string): string {
  const n = typeof amount === 'string' ? parseFloat(amount) : amount
  const code = (currency || 'XPF').toUpperCase()
  if (!isFinite(n)) return code === 'XPF' ? '— F' : '—'
  if (code === 'XPF') return formatXpf(n)

  const decimals = decimalsOf(code)
  try {
    return new Intl.NumberFormat(intlLocale(), {
      style: 'currency',
      currency: code,
      maximumFractionDigits: decimals,
      minimumFractionDigits: decimals,
    }).format(n)
  } catch {
    return `${n.toFixed(decimals)} ${code}`
  }
}
