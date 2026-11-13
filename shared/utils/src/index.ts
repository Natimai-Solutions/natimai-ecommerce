export { formatXpf, formatPrice, formatMoney, parseDecimal } from './currency'
export {
  dayBounds,
  formatDate,
  formatDateTime,
  formatRelative,
  fromShopDateTimeInput,
  todayLocal,
  toShopDateTimeInput,
} from './date'
export {
  configureFormatting,
  decimalsOf,
  formatContext,
  intlLocale,
  setCurrencyDecimals,
  setFormatContextResolver,
} from './format'
export type { FormatContext } from './format'
export { fr as i18nFr } from './i18n/fr'
export type { TranslationKeys } from './i18n/fr'
export { ISO_COUNTRY_CODES, countryLabel, countryOptions } from './countries'
export { orderRef } from './orderRef'
export {
  DEPARTURE_STATUSES,
  departureStatusLabel,
  nextDepartureStatus,
  departureDaysLeft,
  departureCutoffLabel,
  departureDeliveryLabel,
} from './departure'
export type { DepartureLike, DepartureStatus } from './departure'
export type { CountryOption } from './countries'
