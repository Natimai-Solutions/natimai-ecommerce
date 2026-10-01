/**
 * Storefront availability and condition of a product: can it be added to the
 * cart, what to tell the customer, is it new or refurbished. One place for
 * the card, the page and the dialog.
 */

/**
 * Translator of the visitor's language (`useI18n().t`, or a stand-in in
 * tests): the labels below are message keys, never French text.
 */
export type Translate = (key: string, named?: Record<string, unknown>) => string;

/**
 * Sellable quantity as the checkout counts it: warehouse stock plus supplier
 * stock (the latter only when the product has a supplier). Served as
 * `available_quantity` by the storefront endpoints; `supplier_quantity` is the
 * fallback for responses that do not compute it.
 */
export function sellableQuantity(product: {
  available_quantity?: string | number | null;
  supplier_quantity: string | number;
}): number {
  const raw = product.available_quantity ?? product.supplier_quantity;
  const parsed = typeof raw === 'number' ? raw : parseFloat(raw);
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : 0;
}

export interface AvailabilityInput {
  /** Supplier stock at the last refresh (decimal string from the API). For a
   * refurbished lot, the units left in the lot. */
  supplier_quantity: string | number;
  /** Sellable stock (warehouse + supplier) when the API serves it. */
  available_quantity?: string | number | null;
  /** stock | on_demand | continuous | lot — absent on older payloads = stock. */
  availability_mode?: string | null;
  /** Sellable stock held in our warehouse (« chez nous »), variants included. */
  stock_local?: string | number | null;
  /** Sellable stock at the supplier (longer delivery), variants included. */
  stock_supplier?: string | number | null;
}

/**
 * Where the units come from: our warehouse (`local`), the supplier only
 * (`supplier`, longer delivery), bought to order (`order`), none (`none`).
 * `unknown` = in stock but the response does not say where.
 */
export type StockSource = 'local' | 'supplier' | 'order' | 'none' | 'unknown';

export interface Availability {
  /** Add-to-cart allowed. */
  orderable: boolean;
  /** True when the order is served from the next grouped departure, not stock. */
  preorder: boolean;
  /** Stock units to display (0 when none). */
  quantity: number;
  label: string;
  source: StockSource;
  /** Units in our warehouse / at the supplier (0 when unknown). */
  localQuantity: number;
  supplierQuantity: number;
  /** Second line: « + 4 chez le fournisseur », « Délai plus long »… or null. */
  note: string | null;
}

function toQuantity(raw: string | number | null | undefined): number | null {
  if (raw == null) return null;
  const parsed = typeof raw === 'number' ? raw : parseFloat(raw);
  return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : 0;
}

export function productAvailability(product: AvailabilityInput, t: Translate): Availability {
  const quantity = sellableQuantity(product);
  const mode = product.availability_mode ?? 'stock';
  const inStock = quantity > 0;
  const local = toQuantity(product.stock_local);
  const supplier = toQuantity(product.stock_supplier);
  const split = { localQuantity: local ?? 0, supplierQuantity: supplier ?? 0 };

  if (mode === 'continuous' || (mode === 'on_demand' && inStock)) {
    return {
      orderable: true,
      preorder: true,
      quantity,
      label: t('availability.on_order'),
      source: 'order',
      ...split,
      note: null,
    };
  }
  if (mode === 'lot') {
    return inStock
      ? {
          orderable: true,
          preorder: false,
          quantity,
          label: t(quantity > 1 ? 'availability.lot_left_many' : 'availability.lot_left_one', {
            n: quantity,
          }),
          source: local ? 'local' : supplier ? 'supplier' : 'unknown',
          ...split,
          note: null,
        }
      : {
          orderable: false,
          preorder: false,
          quantity: 0,
          label: t('availability.lot_sold_out'),
          source: 'none',
          ...split,
          note: null,
        };
  }
  if (!inStock) {
    return {
      orderable: false,
      preorder: false,
      quantity: 0,
      label: t('availability.unavailable'),
      source: 'none',
      ...split,
      note: null,
    };
  }
  if (local) {
    return {
      orderable: true,
      preorder: false,
      quantity,
      label: t('availability.in_stock_here', { n: local }),
      source: 'local',
      ...split,
      note: supplier ? t('availability.plus_supplier', { n: supplier }) : null,
    };
  }
  if (supplier) {
    return {
      orderable: true,
      preorder: false,
      quantity,
      label: t('availability.in_stock_supplier', { n: supplier }),
      source: 'supplier',
      ...split,
      note: t('availability.longer_delay'),
    };
  }
  // Older payload without the split: the historical label.
  return {
    orderable: true,
    preorder: false,
    quantity,
    label: t('availability.in_stock', { n: quantity }),
    source: 'unknown',
    ...split,
    note: null,
  };
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
export function conditionLabel(product: ConditionInput, t: Translate): string {
  if (!isRefurbished(product)) return t('condition.new');
  const grade = (product.condition_grade ?? '').trim();
  return grade
    ? t('condition.refurbished_grade', { grade: grade.toUpperCase() })
    : t('condition.refurbished');
}

/** Detail lines of a refurbished item (empty for new goods or when nothing is set). */
export function refurbishedDetails(
  product: ConditionInput,
  t: Translate,
): { label: string; value: string }[] {
  if (!isRefurbished(product)) return [];
  const details: { label: string; value: string }[] = [];
  if (product.condition_grade)
    details.push({ label: t('condition.grade'), value: product.condition_grade.toUpperCase() });
  if (product.battery_health_pct != null) {
    details.push({ label: t('condition.battery'), value: `${product.battery_health_pct} %` });
  }
  if (product.os_licence)
    details.push({ label: t('condition.licence'), value: product.os_licence });
  if (product.warranty_months != null) {
    details.push({
      label: t('condition.warranty'),
      value: t('condition.warranty_months', { n: product.warranty_months }),
    });
  }
  return details;
}
