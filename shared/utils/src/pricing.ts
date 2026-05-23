/**
 * Client-side pricing helpers — mirrors the backend formula:
 *
 *   sale_price = cost_in_xpf
 *                × (1 + customs_rate_pct / 100)
 *                × (1 + margin_rate_pct / 100)
 *                × (1 + tax_rate_pct / 100)
 *
 * Used for admin price previews. The authoritative price is always
 * calculated server-side and returned in product.base_price.
 */

export interface PricingInput {
  costAmountXpf: number
  customsRatePct: number
  marginRatePct: number
  taxRatePct: number
}

export interface PricingBreakdown {
  costXpf: number
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
  const { costAmountXpf, customsRatePct, marginRatePct, taxRatePct } = input

  const afterCustoms = costAmountXpf * (1 + customsRatePct / 100)
  const afterMargin = afterCustoms * (1 + marginRatePct / 100)
  const salePrice = afterMargin * (1 + taxRatePct / 100)

  return {
    costXpf: costAmountXpf,
    afterCustoms,
    afterMargin,
    salePrice: Math.round(salePrice),
    customsRatePct,
    marginRatePct,
    taxRatePct,
  }
}
