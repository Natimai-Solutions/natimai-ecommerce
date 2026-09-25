import { describe, expect, it } from 'vitest'

import { conditionLabel, isRefurbished, productAvailability, refurbishedDetails } from './availability'

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

describe('refurbished lots', () => {
  it('counts the units left in the lot and closes it at zero', () => {
    expect(productAvailability({ supplier_quantity: '3', availability_mode: 'lot' })).toEqual({
      orderable: true,
      preorder: false,
      quantity: 3,
      label: '3 exemplaires restants sur ce lot',
    })
    expect(productAvailability({ supplier_quantity: '1', availability_mode: 'lot' }).label).toBe(
      '1 exemplaire restant sur ce lot',
    )
    expect(productAvailability({ supplier_quantity: '0', availability_mode: 'lot' })).toEqual({
      orderable: false,
      preorder: false,
      quantity: 0,
      label: 'Lot épuisé',
    })
  })

  it('labels the condition and lists the refurbished details', () => {
    expect(conditionLabel({})).toBe('Neuf')
    expect(conditionLabel({ condition: 'new' })).toBe('Neuf')
    expect(conditionLabel({ condition: 'refurbished' })).toBe('Reconditionné')
    expect(conditionLabel({ condition: 'refurbished', condition_grade: 'a' })).toBe(
      'Reconditionné · Grade A',
    )
    expect(isRefurbished({ condition: 'refurbished' })).toBe(true)
    expect(refurbishedDetails({ condition: 'new', warranty_months: 24 })).toEqual([])
    expect(
      refurbishedDetails({
        condition: 'refurbished',
        condition_grade: 'b',
        battery_health_pct: 85,
        os_licence: 'Windows 11 Pro',
        warranty_months: 12,
      }),
    ).toEqual([
      { label: 'Grade', value: 'B' },
      { label: 'Batterie', value: '85 %' },
      { label: 'Licence', value: 'Windows 11 Pro' },
      { label: 'Garantie', value: '12 mois' },
    ])
  })
})
