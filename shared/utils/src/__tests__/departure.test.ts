import { describe, expect, it } from 'vitest'
import {
  departureCutoffLabel,
  departureDaysLeft,
  departureDeliveryLabel,
  departureStatusLabel,
  nextDepartureStatus,
} from '../departure'

const departure = {
  name: 'Octobre',
  order_cutoff_at: '2026-10-15T10:00:00Z',
  // Noon UTC: the same calendar day in Tahiti (UTC-10), where dates are shown.
  estimated_delivery_at: '2026-11-10T12:00:00Z',
  status: 'open',
}

describe('departure labels', () => {
  it('counts whole days left before the cutoff', () => {
    expect(departureDaysLeft(departure, new Date('2026-10-12T10:00:00Z'))).toBe(3)
    expect(departureDaysLeft(departure, new Date('2026-10-15T09:00:00Z'))).toBe(0)
    expect(departureDaysLeft(departure, new Date('2026-10-16T10:00:00Z'))).toBe(-1)
    expect(departureDaysLeft({ ...departure, order_cutoff_at: 'nope' })).toBe(0)
  })

  it('formats the cutoff with the countdown', () => {
    expect(departureCutoffLabel(departure, new Date('2026-10-12T10:00:00Z'))).toBe(
      'Commandez avant le 15/10/2026 (plus que 3 jours)',
    )
    expect(departureCutoffLabel(departure, new Date('2026-10-14T11:00:00Z'))).toBe(
      'Commandez avant le 15/10/2026 (dernier jour)',
    )
    expect(departureCutoffLabel(departure, new Date('2026-10-20T10:00:00Z'))).toBe(
      'Commandez avant le 15/10/2026',
    )
  })

  it('formats the delivery estimate only when set', () => {
    expect(departureDeliveryLabel(departure)).toBe('Livraison estimée le 10/11/2026')
    expect(departureDeliveryLabel({ ...departure, estimated_delivery_at: null })).toBeNull()
  })

  it('labels statuses and walks the lifecycle', () => {
    expect(departureStatusLabel('open')).toBe('Ouvert aux commandes')
    expect(departureStatusLabel('whatever')).toBe('whatever')
    expect(nextDepartureStatus('open')).toBe('closed')
    expect(nextDepartureStatus('distributed')).toBeNull()
    expect(nextDepartureStatus('whatever')).toBeNull()
  })
})
