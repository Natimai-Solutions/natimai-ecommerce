/**
 * Storefront availability of a product: can it be added to the cart, and
 * what to tell the customer. One place for the card, the page and the dialog.
 */

export interface AvailabilityInput {
  /** Supplier stock at the last refresh (decimal string from the API). */
  supplier_quantity: string | number;
  /** stock | on_demand | continuous — absent on older payloads = stock. */
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
  if (inStock) {
    return { orderable: true, preorder: false, quantity, label: `${quantity} en stock` };
  }
  return { orderable: false, preorder: false, quantity: 0, label: 'Indisponible' };
}
