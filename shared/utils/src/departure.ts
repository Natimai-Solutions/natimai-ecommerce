/**
 * Grouped departures (« départs groupés ») — labels shared by the storefront
 * banner / product page / checkout and the admin screen.
 */

import { formatDate } from './date'

/** The customer-facing shape (`GroupedDepartureSummary`); the admin one is a superset. */
export interface DepartureLike {
  name: string
  order_cutoff_at: string
  estimated_delivery_at?: string | null
  departure_at?: string | null
  status: string
}

/** Lifecycle, in order (mirrors the backend `DEPARTURE_STATUSES`). */
export const DEPARTURE_STATUSES = [
  'draft',
  'open',
  'closed',
  'ordered',
  'in_transit',
  'at_customs',
  'received',
  'distributed',
] as const

export type DepartureStatus = (typeof DEPARTURE_STATUSES)[number]

const STATUS_LABELS: Record<DepartureStatus, string> = {
  draft: 'Brouillon',
  open: 'Ouvert aux commandes',
  closed: 'Clôturé',
  ordered: 'Commandé au fournisseur',
  in_transit: 'En transit',
  at_customs: 'En douane',
  received: 'Reçu, contrôle en cours',
  distributed: 'Distribué',
}

export function departureStatusLabel(status: string): string {
  return (STATUS_LABELS as Record<string, string>)[status] ?? status
}

/** The status that follows `status`, or null once distributed / unknown. */
export function nextDepartureStatus(status: string): DepartureStatus | null {
  const index = DEPARTURE_STATUSES.indexOf(status as DepartureStatus)
  if (index < 0 || index === DEPARTURE_STATUSES.length - 1) return null
  return DEPARTURE_STATUSES[index + 1] ?? null
}

/** Whole days left before the order cutoff (0 on the last day, negative after). */
export function departureDaysLeft(d: DepartureLike, now: Date = new Date()): number {
  const ms = new Date(d.order_cutoff_at).getTime() - now.getTime()
  if (Number.isNaN(ms)) return 0
  return Math.floor(ms / 86_400_000)
}

/** « Commandez avant le 15/10/2026 (plus que 3 jours) » */
export function departureCutoffLabel(d: DepartureLike, now: Date = new Date()): string {
  const base = `Commandez avant le ${formatDate(d.order_cutoff_at)}`
  const days = departureDaysLeft(d, now)
  if (days < 0) return base
  if (days === 0) return `${base} (dernier jour)`
  return `${base} (plus que ${days} jour${days > 1 ? 's' : ''})`
}

/** « Livraison estimée le 10/11/2026 », or null when no estimate is set. */
export function departureDeliveryLabel(d: DepartureLike): string | null {
  if (!d.estimated_delivery_at) return null
  return `Livraison estimée le ${formatDate(d.estimated_delivery_at)}`
}
