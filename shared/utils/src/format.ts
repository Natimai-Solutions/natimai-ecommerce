/**
 * Formatting context shared by the money and date helpers (R7 / L4-L5).
 *
 * The storefront and the admin set it once from `GET /system/config` (shop
 * time zone, default language) and again whenever the visitor switches
 * language. Until then the historical values apply (French, Tahiti), so a
 * helper called before the configuration loads still renders sensibly.
 */

export interface FormatContext {
  /** BCP 47 language of the interface: `fr`, `en`… */
  locale: string
  /** IANA time zone of dates shown to customers. */
  timeZone: string
}

const context: FormatContext = { locale: 'fr', timeZone: 'Pacific/Tahiti' }

/** Number of decimals per currency, as published by the backend. */
const currencyDecimals = new Map<string, number>([['XPF', 0]])

export function configureFormatting(next: Partial<FormatContext>): void {
  if (next.locale) context.locale = next.locale
  if (next.timeZone) context.timeZone = next.timeZone
}

export function formatContext(): Readonly<FormatContext> {
  return context
}

/** Declare the decimals of currencies (from `/currency/display-rates`). */
export function setCurrencyDecimals(values: Record<string, number>): void {
  for (const [code, decimals] of Object.entries(values)) {
    if (Number.isInteger(decimals) && decimals >= 0 && decimals <= 4) {
      currencyDecimals.set(code.toUpperCase(), decimals)
    }
  }
}

/** Decimals of a currency: declared by the backend, else ISO 4217 (Intl). */
export function decimalsOf(currency: string): number {
  const code = currency.toUpperCase()
  const known = currencyDecimals.get(code)
  if (known !== undefined) return known
  try {
    return (
      new Intl.NumberFormat('en', { style: 'currency', currency: code }).resolvedOptions()
        .maximumFractionDigits ?? 2
    )
  } catch {
    return 2
  }
}

/**
 * Locale tag used for numbers and dates: French keeps the territory's
 * conventions (`fr-PF` when the shop lives in Tahiti), other languages
 * their own defaults.
 */
export function intlLocale(locale: string = context.locale): string {
  const base = locale.toLowerCase()
  if (base === 'fr' || base.startsWith('fr-')) {
    return context.timeZone === 'Pacific/Tahiti' ? 'fr-PF' : 'fr-FR'
  }
  if (base === 'en') return 'en-GB'
  return locale
}
