import { describe, it, expect } from 'vitest'

import { ISO_COUNTRY_CODES, countryLabel, countryOptions } from '../countries'

describe('ISO_COUNTRY_CODES', () => {
  it('contains only unique 2-letter uppercase codes', () => {
    expect(new Set(ISO_COUNTRY_CODES).size).toBe(ISO_COUNTRY_CODES.length)
    for (const code of ISO_COUNTRY_CODES) {
      expect(code).toMatch(/^[A-Z]{2}$/)
    }
  })

  it('includes the local market and neighbouring territories', () => {
    for (const code of ['PF', 'FR', 'NC', 'WF', 'US', 'NZ']) {
      expect(ISO_COUNTRY_CODES).toContain(code)
    }
  })
})

describe('countryLabel', () => {
  it('localizes a code in French', () => {
    expect(countryLabel('PF')).toBe('Polynésie française')
    expect(countryLabel('de')).toBe('Allemagne')
  })

  it('falls back to the code for unassigned regions', () => {
    // QQ is in the ISO private-use range — CLDR has no display name for it.
    expect(countryLabel('QQ')).toBe('QQ')
  })

  it('passes legacy free-text countries through untouched', () => {
    expect(countryLabel(' Polynésie française ')).toBe('Polynésie française')
  })
})

describe('countryOptions', () => {
  it('pins PF and FR on top by default, then sorts alphabetically', () => {
    const options = countryOptions()
    expect(options[0]?.value).toBe('PF')
    expect(options[1]?.value).toBe('FR')
    const rest = options.slice(2).map((o) => o.label)
    expect(rest).toEqual([...rest].sort((a, b) => a.localeCompare(b, 'fr')))
  })

  it('keeps the ISO code as the option value and in the label', () => {
    const pf = countryOptions().find((o) => o.value === 'PF')
    expect(pf?.label).toBe('Polynésie française (PF)')
  })
})
