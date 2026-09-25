/**
 * Storefront availability and condition of a product: can it be added to the
 * cart, what to tell the customer, is it new or refurbished. One place for
 * the card, the page and the dialog.
 */

export interface AvailabilityInput {
  /** Supplier stock at the last refresh (decimal string from the API). For a
   * refurbished lot, the units left in the lot. */
  supplier_quantity: string | number;
  /** stock | on_demand | continuous | lot — absent on older payloads = stock. */
  availability_mode?: string | null;
}

export interface Availability {
  /** Add-to-cart allowed. */
  orderable: boolean;
  /** True when the order is served from the next grouped departure, not stock. */
  preorder: boolean;
  /** Stock units to display (0 when none). */
  quantity: number;
  label: string;
}

export function productAvailability(product: AvailabilityInput): Availability {
  const quantity = Math.max(0, Math.round(Number(product.supplier_quantity) || 0));
  const mode = product.availability_mode ?? 'stock';
  const inStock = quantity > 0;

  if (mode === 'continuous' || (mode === 'on_demand' && inStock)) {
    return { orderable: true, preorder: true, quantity, label: 'Sur commande' };
  }
  if (mode === 'lot') {
    return inStock
      ? {
          orderable: true,
          preorder: false,
          quantity,
          label: `${quantity} exemplaire${quantity > 1 ? 's' : ''} restant${quantity > 1 ? 's' : ''} sur ce lot`,
        }
      : { orderable: false, preorder: false, quantity: 0, label: 'Lot épuisé' };
  }
  if (inStock) {
    return { orderable: true, preorder: false, quantity, label: `${quantity} en stock` };
  }
  return { orderable: false, preorder: false, quantity: 0, label: 'Indisponible' };
}

export interface ConditionInput {
  /** new | refurbished — absent on older payloads = new. */
  condition?: string | null;
  condition_grade?: string | null;
  battery_health_pct?: number | null;
  os_licence?: string | null;
  warranty_months?: number | null;
}

export function isRefurbished(product: ConditionInput): boolean {
  return product.condition === 'refurbished';
}

/** « Reconditionné · Grade A » / « Neuf » — the badge text. */
export function conditionLabel(product: ConditionInput): string {
  if (!isRefurbished(product)) return 'Neuf';
  const grade = (product.condition_grade ?? '').trim();
  return grade ? `Reconditionné · Grade ${grade.toUpperCase()}` : 'Reconditionné';
}

/** Detail lines of a refurbished item (empty for new goods or when nothing is set). */
export function refurbishedDetails(product: ConditionInput): { label: string; value: string }[] {
  if (!isRefurbished(product)) return [];
  const details: { label: string; value: string }[] = [];
  if (product.condition_grade) details.push({ label: 'Grade', value: product.condition_grade.toUpperCase() });
  if (product.battery_health_pct != null) {
    details.push({ label: 'Batterie', value: `${product.battery_health_pct} %` });
  }
  if (product.os_licence) details.push({ label: 'Licence', value: product.os_licence });
  if (product.warranty_months != null) {
    details.push({ label: 'Garantie', value: `${product.warranty_months} mois` });
  }
  return details;
}
