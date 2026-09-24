import { describe, expect, it } from 'vitest'

import { productAvailability } from './availability'

describe('productAvailability', () => {
  it('keeps the historical behaviour for stock products', () => {
    expect(productAvailability({ supplier_quantity: '3.00' })).toEqual({
      orderable: true,
      preorder: false,
      quantity: 3,
      label: '3 en stock',
    })
    expect(productAvailability({ supplier_quantity: '0.00', availability_mode: 'stock' })).toEqual(
      { orderable: false, preorder: false, quantity: 0, label: 'Indisponible' },
    )
  })

  it('accepts pre-orders while the supplier shows stock', () => {
    const onDemand = productAvailability({ supplier_quantity: '1', availability_mode: 'on_demand' })
    expect(onDemand.orderable).toBe(true)
    expect(onDemand.preorder).toBe(true)
    expect(onDemand.label).toBe('Sur commande')
    expect(productAvailability({ supplier_quantity: '0', availability_mode: 'on_demand' }).orderable).toBe(
      false,
    )
  })

  it('always accepts continuous products', () => {
    const continuous = productAvailability({ supplier_quantity: '0', availability_mode: 'continuous' })
    expect(continuous).toEqual({ orderable: true, preorder: true, quantity: 0, label: 'Sur commande' })
  })

  it('treats a malformed quantity as none', () => {
    expect(productAvailability({ supplier_quantity: 'abc' }).orderable).toBe(false)
  })
})
