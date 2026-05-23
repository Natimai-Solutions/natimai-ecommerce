/**
 * Formatting for XPF (Franc Pacifique).
 *
 * XPF has no decimal places.
 * Format: "12 500 F" (non-breaking space as thousands separator)
 */

const XPF_LOCALE = 'fr-PF'

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
    new Intl.NumberFormat(XPF_LOCALE, {
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
