/**
 * Client-side pricing helpers — mirrors the backend formula:
 *
 * Corrected formula (CAF customs base — Polynésie française):
 *
 *   caf        = costInReference + freightInReference + insuranceInReference
 *   afterCustoms = caf × (1 + customs_rate_pct / 100)
 *   afterMargin  = afterCustoms × (1 + margin_rate_pct / 100)
 *   salePrice    = afterMargin × (1 + tax_rate_pct / 100)
 *
 * ``freightInReference`` is the variable import-freight component
 * (price_per_kg × billable_weight) for the chosen service level.
 * ``insuranceInReference`` defaults to 0 (driven by INSURANCE_RATE_PCT on
 * the backend; include it here only when the server sends it).
 *
 * When no import route has been chosen yet (admin preview / no shipping data),
 * omit both fields — they default to 0 and the formula degrades gracefully.
 *
 * The authoritative price is always calculated server-side. This helper is
 * used for instant client-side dropdown switching without a refetch.
 */

export interface PricingInput {
  costInReference: number
  customsRatePct: number
  marginRatePct: number
  taxRatePct: number
  /** Variable import freight (price_per_kg × billable_weight). Default 0. */
  freightInReference?: number
  /** Insurance on cost (driven by INSURANCE_RATE_PCT). Default 0. */
  insuranceInReference?: number
}

export interface PricingBreakdown {
  costInReference: number
  freightInReference: number
  insuranceInReference: number
  caf: number
  afterCustoms: number
  afterMargin: number
  salePrice: number
  customsRatePct: number
  marginRatePct: number
  taxRatePct: number
}

/**
 * Calculate sale price and return a full breakdown.
 */
export function calculateSalePrice(input: PricingInput): PricingBreakdown {
  const {
    costInReference,
    customsRatePct,
    marginRatePct,
    taxRatePct,
    freightInReference = 0,
    insuranceInReference = 0,
  } = input

  const caf = costInReference + freightInReference + insuranceInReference
  const afterCustoms = caf * (1 + customsRatePct / 100)
  const afterMargin = afterCustoms * (1 + marginRatePct / 100)
  const salePrice = afterMargin * (1 + taxRatePct / 100)

  return {
    costInReference,
    freightInReference,
    insuranceInReference,
    caf,
    afterCustoms,
    afterMargin,
    salePrice: Math.round(salePrice),
    customsRatePct,
    marginRatePct,
    taxRatePct,
  }
}
