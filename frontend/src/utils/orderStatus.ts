import type { StatusTone } from '@app/ui/statusTone';

import type { Translate } from './availability';

/**
 * Présentation client des statuts de commande.
 *
 * Le backend porte un seul statut qui mêle paiement et acheminement
 * (`PAYMENT_STATUSES` + `FULFILLMENT_STATUSES` dans
 * `order/services/status.py`). La vitrine l'affiche en deux facettes :
 * où en est le paiement, où en est la livraison. Les libellés sont des clés
 * de message (`order_status.payment.*`, `order_status.delivery.*`).
 */
export interface StatusFacet {
  label: string;
  tone: StatusTone;
  icon: string;
}

interface FacetSpec {
  key: string;
  tone: StatusTone;
  icon: string;
}

const PAID: FacetSpec = { key: 'payment.paid', tone: 'ok', icon: 'ph:check-circle' };

const PAYMENT_FACETS: Record<string, FacetSpec> = {
  Pending: { key: 'payment.pending', tone: 'warn', icon: 'ph:clock' },
  AwaitingPayment: { key: 'payment.awaiting', tone: 'warn', icon: 'ph:clock' },
  PartiallyPaid: { key: 'payment.partially_paid', tone: 'warn', icon: 'ph:coins' },
  Paid: PAID,
  DepositPaid: { key: 'payment.deposit_paid', tone: 'ok', icon: 'ph:piggy-bank' },
  PaymentFailed: { key: 'payment.failed', tone: 'danger', icon: 'ph:x-circle' },
  PaymentReview: { key: 'payment.review', tone: 'warn', icon: 'ph:magnifying-glass' },
  Refunded: { key: 'payment.refunded', tone: 'neutral', icon: 'ph:arrow-u-up-left' },
  PartiallyRefunded: {
    key: 'payment.partially_refunded',
    tone: 'neutral',
    icon: 'ph:arrow-u-up-left',
  },
  Cancelled: { key: 'payment.cancelled', tone: 'neutral', icon: 'ph:prohibit' },
  // Acheminement : le paiement est acquis.
  Processing: PAID,
  Shipped: PAID,
  Delivered: PAID,
  OrderedFromSupplier: PAID,
  InTransit: PAID,
  AtCustoms: PAID,
  Received: PAID,
  ReadyForPickup: PAID,
  Backordered: PAID,
};

const PREPARING: FacetSpec = { key: 'delivery.preparing', tone: 'neutral', icon: 'ph:package' };

const DELIVERY_FACETS: Record<string, FacetSpec> = {
  Paid: PREPARING,
  DepositPaid: PREPARING,
  Processing: PREPARING,
  OrderedFromSupplier: {
    key: 'delivery.ordered_from_supplier',
    tone: 'neutral',
    icon: 'ph:storefront',
  },
  InTransit: { key: 'delivery.in_transit', tone: 'neutral', icon: 'ph:airplane-tilt' },
  AtCustoms: { key: 'delivery.at_customs', tone: 'neutral', icon: 'ph:gavel' },
  Received: { key: 'delivery.received', tone: 'neutral', icon: 'ph:package' },
  Shipped: { key: 'delivery.shipped', tone: 'neutral', icon: 'ph:truck' },
  ReadyForPickup: { key: 'delivery.ready_for_pickup', tone: 'ok', icon: 'ph:storefront' },
  Delivered: { key: 'delivery.delivered', tone: 'ok', icon: 'ph:check-circle' },
  Backordered: { key: 'delivery.backordered', tone: 'warn', icon: 'ph:warning' },
};

function present(spec: FacetSpec, t: Translate): StatusFacet {
  return { label: t(`order_status.${spec.key}`), tone: spec.tone, icon: spec.icon };
}

/** Facette « paiement » d'un statut de commande (toujours définie). */
export function paymentFacet(statusName: string | null | undefined, t: Translate): StatusFacet {
  if (!statusName) return present(PAYMENT_FACETS.Pending!, t);
  const spec = PAYMENT_FACETS[statusName];
  return spec
    ? present(spec, t)
    : { label: humanize(statusName), tone: 'neutral', icon: 'ph:info' };
}

/** Facette « livraison », absente tant que la commande n'est pas réglée. */
export function deliveryFacet(
  statusName: string | null | undefined,
  t: Translate,
): StatusFacet | null {
  const spec = statusName ? DELIVERY_FACETS[statusName] : undefined;
  return spec ? present(spec, t) : null;
}

/** Libellé court d'un statut, pour un titre ou une liste. */
export function orderStatusLabel(statusName: string | null | undefined, t: Translate): string {
  return (deliveryFacet(statusName, t) ?? paymentFacet(statusName, t)).label;
}

/** Libellé d'un type de livraison connu (`order_status.delivery_type.*`). */
export const DELIVERY_TYPES: readonly string[] = ['pickup', 'home_delivery', 'air_freight'];

/** `PaymentReview` → « Payment review » : jamais un nom de code brut en vitrine. */
export function humanize(code: string): string {
  const spaced = code
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
