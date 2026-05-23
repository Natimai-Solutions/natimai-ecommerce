/**
 * Date formatting for French Polynesia.
 *
 * Timezone: Pacific/Tahiti (UTC-10, no DST)
 * Format:   DD/MM/YYYY (French convention)
 */

const TZ = 'Pacific/Tahiti'
const LOCALE = 'fr-PF'

/**
 * Format an ISO date string as DD/MM/YYYY in Tahiti timezone.
 */
export function formatDate(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    return new Intl.DateTimeFormat(LOCALE, {
      timeZone: TZ,
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
    return new Intl.DateTimeFormat(LOCALE, {
      timeZone: TZ,
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
 * Returns a relative label ("il y a 2 jours") for recent dates.
 */
export function formatRelative(isoString: string | null | undefined): string {
  if (!isoString) return '—'
  try {
    const diff = Date.now() - new Date(isoString).getTime()
    const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })
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
