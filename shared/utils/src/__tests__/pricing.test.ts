import { describe, it, expect } from 'vitest'

import { calculateSalePrice } from '../pricing'

describe('calculateSalePrice', () => {
  it('applies CAF → customs → margin → tax and rounds the sale price', () => {
    const b = calculateSalePrice({
      costInReference: 1000,
      freightInReference: 100,
      insuranceInReference: 0,
      customsRatePct: 10,
      marginRatePct: 20,
      taxRatePct: 5,
    })

    expect(b.caf).toBe(1100) // 1000 + 100 + 0
    expect(b.afterCustoms).toBeCloseTo(1210) // 1100 × 1.10
    expect(b.afterMargin).toBeCloseTo(1452) // 1210 × 1.20
    expect(b.salePrice).toBe(1525) // 1452 × 1.05 = 1524.6 → round
  })

  it('defaults freight and insurance to 0 when omitted', () => {
    const b = calculateSalePrice({
      costInReference: 1000,
      customsRatePct: 0,
      marginRatePct: 0,
      taxRatePct: 0,
    })

    expect(b.freightInReference).toBe(0)
    expect(b.insuranceInReference).toBe(0)
    expect(b.caf).toBe(1000)
    expect(b.salePrice).toBe(1000)
  })

  it('includes insurance in the CAF customs base', () => {
    const b = calculateSalePrice({
      costInReference: 1000,
      freightInReference: 100,
      insuranceInReference: 50,
      customsRatePct: 0,
      marginRatePct: 0,
      taxRatePct: 0,
    })

    expect(b.caf).toBe(1150)
    expect(b.salePrice).toBe(1150)
  })
})
