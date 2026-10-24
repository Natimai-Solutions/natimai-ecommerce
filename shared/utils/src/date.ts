/**
 * Date formatting in the shop's time zone and the interface's language
 * (`configureFormatting`, R7 / L5). Defaults: Pacific/Tahiti, French
 * (DD/MM/YYYY).
 */

import { formatContext, intlLocale } from './format'

/**
 * Format an ISO date string as DD/MM/YYYY in Tahiti timezone.
 */
export function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    return new Intl.DateTimeFormat(intlLocale(), {
      timeZone: formatContext().timeZone,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(isoString))
  } catch {
    return isoString
  }
}

/**
 * Format an ISO datetime string as "DD/MM/YYYY HH:mm" in Tahiti timezone.
 */
export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    return new Intl.DateTimeFormat(intlLocale(), {
      timeZone: formatContext().timeZone,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(isoString))
  } catch {
    return isoString
  }
}

/**
 * Returns a relative label ("il y a 2 jours", "2 days ago") for recent dates.
 */
export function formatRelative(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    const diff = Date.now() - new Date(isoString).getTime()
    const rtf = new Intl.RelativeTimeFormat(formatContext().locale, { numeric: 'auto' })
    const seconds = Math.round(diff / 1000)
    if (seconds < 60) return rtf.format(-seconds, 'second')
    const minutes = Math.round(seconds / 60)
    if (minutes < 60) return rtf.format(-minutes, 'minute')
    const hours = Math.round(minutes / 60)
    if (hours < 24) return rtf.format(-hours, 'hour')
    const days = Math.round(hours / 24)
    return rtf.format(-days, 'day')
  } catch {
    return formatDate(isoString)
  }
}

/** `YYYY-MM-DD` of `moment` on the calendar of the shop's time zone. */
function calendarDay(moment: Date, timeZone: string): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(moment)
}

/**
 * Today (`YYYY-MM-DD`) in the shop's time zone — a business date.
 *
 * Never `new Date().toISOString().slice(0, 10)`: that is the UTC day, the
 * next day in Tahiti from 14:00 on.
 */
export function todayLocal(now: Date = new Date()): string {
  return calendarDay(now, formatContext().timeZone)
}

/** Offset of `timeZone` from UTC at `moment`, as `±HH:MM`. */
function zoneOffset(moment: Date, timeZone: string): string {
  const name =
    new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'longOffset' })
      .formatToParts(moment)
      .find((part) => part.type === 'timeZoneName')?.value ?? 'GMT'
  const offset = name.replace('GMT', '')
  return offset === '' ? '+00:00' : offset
}

/**
 * The first and last instants (ISO 8601 with the zone offset) of a business
 * day of the shop: what an API filter on timestamps needs to cover the whole
 * day as the shop sees it, not the UTC day.
 */
export function dayBounds(day: string): { start: string; end: string } {
  const timeZone = formatContext().timeZone
  // Noon of that day: the offset in force that day, away from any change.
  const offset = zoneOffset(new Date(`${day}T12:00:00Z`), timeZone)
  return { start: `${day}T00:00:00${offset}`, end: `${day}T23:59:59.999${offset}` }
}
