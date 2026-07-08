/**
 * ISO 3166-1 alpha-2 country codes + localized labels.
 *
 * Labels come from `Intl.DisplayNames` (full ICU ships with Node 18+ and every
 * evergreen browser), so no hand-maintained name table: only the code list is
 * static. Backend address/place records store the 2-letter code.
 */

export const ISO_COUNTRY_CODES: readonly string[] = [
  'AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AO', 'AR', 'AS', 'AT', 'AU',
  'AW', 'AX', 'AZ', 'BA', 'BB', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ',
  'BL', 'BM', 'BN', 'BO', 'BQ', 'BR', 'BS', 'BT', 'BW', 'BY', 'BZ', 'CA',
  'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR',
  'CU', 'CV', 'CW', 'CX', 'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ',
  'EC', 'EE', 'EG', 'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK', 'FM', 'FO',
  'FR', 'GA', 'GB', 'GD', 'GE', 'GF', 'GG', 'GH', 'GI', 'GL', 'GM', 'GN',
  'GP', 'GQ', 'GR', 'GT', 'GU', 'GW', 'GY', 'HK', 'HN', 'HR', 'HT', 'HU',
  'ID', 'IE', 'IL', 'IM', 'IN', 'IO', 'IQ', 'IR', 'IS', 'IT', 'JE', 'JM',
  'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM', 'KN', 'KP', 'KR', 'KW', 'KY',
  'KZ', 'LA', 'LB', 'LC', 'LI', 'LK', 'LR', 'LS', 'LT', 'LU', 'LV', 'LY',
  'MA', 'MC', 'MD', 'ME', 'MF', 'MG', 'MH', 'MK', 'ML', 'MM', 'MN', 'MO',
  'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA',
  'NC', 'NE', 'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM',
  'PA', 'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM', 'PN', 'PR', 'PS', 'PT',
  'PW', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD',
  'SE', 'SG', 'SH', 'SI', 'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS',
  'ST', 'SV', 'SX', 'SY', 'SZ', 'TC', 'TD', 'TF', 'TG', 'TH', 'TJ', 'TK',
  'TL', 'TM', 'TN', 'TO', 'TR', 'TT', 'TV', 'TW', 'TZ', 'UA', 'UG', 'US',
  'UY', 'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN', 'VU', 'WF', 'WS', 'YE',
  'YT', 'ZA', 'ZM', 'ZW',
]

export interface CountryOption {
  /** Localized display name, e.g. "Polynésie française (PF)". */
  label: string
  /** ISO 3166-1 alpha-2 code, e.g. "PF" — what the backend stores. */
  value: string
}

/** Localized name of a country code (falls back to the input itself).
 *
 * Non-ISO input (legacy free-text countries like "Polynésie française") is
 * returned untouched so it stays readable wherever it is displayed.
 */
export function countryLabel(code: string, locale = 'fr'): string {
  const trimmed = code.trim()
  if (!/^[A-Za-z]{2}$/.test(trimmed)) return trimmed
  const normalized = trimmed.toUpperCase()
  try {
    const names = new Intl.DisplayNames([locale], { type: 'region' })
    return names.of(normalized) ?? normalized
  } catch {
    return normalized
  }
}

/**
 * Selectable country options: pinned codes first (local market), then the
 * rest sorted alphabetically on the localized label.
 */
export function countryOptions(
  locale = 'fr',
  pinned: readonly string[] = ['PF', 'FR'],
): CountryOption[] {
  const toOption = (code: string): CountryOption => ({
    label: `${countryLabel(code, locale)} (${code})`,
    value: code,
  })
  const pinnedSet = new Set(pinned)
  const rest = ISO_COUNTRY_CODES.filter((code) => !pinnedSet.has(code))
    .map(toOption)
    .sort((a, b) => a.label.localeCompare(b.label, locale))
  return [...pinned.filter((code) => ISO_COUNTRY_CODES.includes(code)).map(toOption), ...rest]
}
