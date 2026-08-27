import { describe, it, expect } from 'vitest'

import { orderRef } from '../orderRef'

const ORDER_UUID = 'e090fee1-2b5d-4a7c-9f3e-8d1c6b4a2e90'

describe('orderRef', () => {
  it('prefers the sequential order number', () => {
    expect(orderRef('CMD-2026-00042', ORDER_UUID)).toBe('CMD-2026-00042')
  })

  it('falls back to the UUID short-ref for orders predating M5', () => {
    expect(orderRef(null, ORDER_UUID)).toBe('#e090fee1')
    expect(orderRef(undefined, ORDER_UUID)).toBe('#e090fee1')
    expect(orderRef('   ', ORDER_UUID)).toBe('#e090fee1')
  })

  it('matches the backend short-ref, which shortens the hex form', () => {
    // The backend parses the UUID and takes 8 chars of `.hex` (no hyphens);
    // slicing the raw string would diverge for any UUID with an early hyphen.
    expect(orderRef(null, '00000000-1111-2222-3333-444444444444')).toBe('#00000000')
    expect(orderRef(null, 'e09-0fee1-2b5d-4a7c-9f3e-8d1c6b4a2e9')).toBe('#e090fee1')
  })

  it('returns a placeholder when nothing identifies the order', () => {
    expect(orderRef(null, null)).toBe('—')
    expect(orderRef('', '')).toBe('—')
  })
})
