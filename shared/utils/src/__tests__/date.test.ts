import { describe, it, expect, vi } from 'vitest'

import { formatDate, formatDateTime, formatRelative } from '../date'

describe('formatDate', () => {
  it('formats an ISO date as DD/MM/YYYY in Tahiti time', () => {
    // Midday UTC stays the same calendar day in Tahiti (UTC-10).
    expect(formatDate('2026-06-23T12:00:00Z')).toBe('23/06/2026')
  })

  it('returns a placeholder for null / undefined', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate(undefined)).toBe('—')
  })

  it('returns the input unchanged on an invalid date', () => {
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })
})

describe('formatDateTime', () => {
  it('returns a placeholder for null', () => {
    expect(formatDateTime(null)).toBe('—')
  })

  it('includes the day for a valid datetime', () => {
    expect(formatDateTime('2026-06-23T12:00:00Z')).toContain('23/06/2026')
  })
})

describe('formatRelative', () => {
  it('returns a placeholder for null', () => {
    expect(formatRelative(null)).toBe('—')
  })

  it('produces a relative label across seconds / minutes / hours / days', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-23T12:00:00Z'))
    try {
      expect(formatRelative('2026-06-23T11:59:30Z')).not.toBe('—') // ~30s ago
      expect(formatRelative('2026-06-23T11:30:00Z')).not.toBe('—') // ~30 min ago
      expect(formatRelative('2026-06-23T08:00:00Z')).not.toBe('—') // ~4 h ago
      expect(formatRelative('2026-06-20T12:00:00Z')).not.toBe('—') // ~3 days ago
    } finally {
      vi.useRealTimers()
    }
  })
})
