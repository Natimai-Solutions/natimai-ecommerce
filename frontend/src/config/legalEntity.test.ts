import { describe, it, expect } from 'vitest'

import {
  isLegalPlaceholder,
  LEGAL_FIELDS,
  LEGAL_FIELD_KEYS,
  LEGAL_PLACEHOLDER_PREFIX,
  resolveLegalEntity,
} from './legalEntity'

describe('isLegalPlaceholder', () => {
  it('recognises an unfilled value', () => {
    expect(isLegalPlaceholder(`${LEGAL_PLACEHOLDER_PREFIX} : n° TAHITI]`)).toBe(true)
  })

  it('leaves a real value alone', () => {
    expect(isLegalPlaceholder('SARL au capital de 1 000 000 XPF')).toBe(false)
    expect(isLegalPlaceholder('')).toBe(false)
  })
})

describe('resolveLegalEntity', () => {
  it('uses the values served by the API', () => {
    const entity = resolveLegalEntity({
      legal_trading_name: 'Natimai Solutions',
      legal_tahiti_number: 'A123456',
    })

    expect(entity.tradingName).toBe('Natimai Solutions')
    expect(entity.tahitiNumber).toBe('A123456')
  })

  it('falls back to a flaggable placeholder for anything missing', () => {
    const entity = resolveLegalEntity({})

    // Every field must still be a string: a legal page rendering "undefined"
    // is worse than one saying the value is missing.
    for (const { field } of LEGAL_FIELDS) {
      expect(typeof entity[field], field).toBe('string')
      expect(isLegalPlaceholder(entity[field]), field).toBe(true)
    }
  })

  it('treats a blank value as missing', () => {
    // An empty system_settings row is the normal state before launch; it must
    // not render as a silent gap in the middle of a sentence.
    const entity = resolveLegalEntity({ legal_form: '   ' })
    expect(isLegalPlaceholder(entity.legalForm)).toBe(true)
  })

  it('ignores keys it does not know', () => {
    const entity = resolveLegalEntity({ default_display_currency: 'XPF' })
    expect(Object.values(entity).every((v) => isLegalPlaceholder(v))).toBe(true)
  })
})

describe('LEGAL_FIELD_KEYS', () => {
  it('mirrors the field mapping without duplicates', () => {
    expect(LEGAL_FIELD_KEYS.size).toBe(LEGAL_FIELDS.length)
    for (const { key } of LEGAL_FIELDS) {
      // The backend whitelists exactly these keys on the public endpoint; a
      // typo here means the field silently never arrives.
      expect(key.startsWith('legal_'), key).toBe(true)
    }
  })
})
