import type { StatusTone } from '@app/ui/statusTone';

/**
 * Présentation client des statuts de commande.
 *
 * Le backend porte un seul statut qui mêle paiement et acheminement
 * (`PAYMENT_STATUSES` + `FULFILLMENT_STATUSES` dans
 * `order/services/status.py`). La vitrine l'affiche en deux facettes :
 * où en est le paiement, où en est la livraison.
 */
export interface StatusFacet {
  label: string;
  tone: StatusTone;
  icon: string;
}

const PAID: StatusFacet = { label: 'Payée', tone: 'ok', icon: 'ph:check-circle' };

const PAYMENT_FACETS: Record<string, StatusFacet> = {
  Pending: { label: 'Paiement en attente', tone: 'warn', icon: 'ph:clock' },
  AwaitingPayment: { label: 'En attente de paiement', tone: 'warn', icon: 'ph:clock' },
  PartiallyPaid: { label: 'Partiellement payée', tone: 'warn', icon: 'ph:coins' },
  Paid: PAID,
  DepositPaid: { label: 'Acompte versé', tone: 'ok', icon: 'ph:piggy-bank' },
  PaymentFailed: { label: 'Paiement refusé', tone: 'danger', icon: 'ph:x-circle' },
  PaymentReview: { label: 'Paiement en vérification', tone: 'warn', icon: 'ph:magnifying-glass' },
  Refunded: { label: 'Remboursée', tone: 'neutral', icon: 'ph:arrow-u-up-left' },
  PartiallyRefunded: {
    label: 'Remboursée en partie',
    tone: 'neutral',
    icon: 'ph:arrow-u-up-left',
  },
  Cancelled: { label: 'Annulée', tone: 'neutral', icon: 'ph:prohibit' },
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

const PREPARING: StatusFacet = { label: 'En préparation', tone: 'neutral', icon: 'ph:package' };

const DELIVERY_FACETS: Record<string, StatusFacet> = {
  Paid: PREPARING,
  DepositPaid: PREPARING,
  Processing: PREPARING,
  OrderedFromSupplier: {
    label: 'Commandée au fournisseur',
    tone: 'neutral',
    icon: 'ph:storefront',
  },
  InTransit: { label: 'En transit', tone: 'neutral', icon: 'ph:airplane-tilt' },
  AtCustoms: { label: 'En douane', tone: 'neutral', icon: 'ph:gavel' },
  Received: { label: 'Reçue, contrôle en cours', tone: 'neutral', icon: 'ph:package' },
  Shipped: { label: 'Expédiée', tone: 'neutral', icon: 'ph:truck' },
  ReadyForPickup: { label: 'Disponible au retrait', tone: 'ok', icon: 'ph:storefront' },
  Delivered: { label: 'Livrée', tone: 'ok', icon: 'ph:check-circle' },
  Backordered: { label: 'Rupture, report', tone: 'warn', icon: 'ph:warning' },
};

/** Facette « paiement » d'un statut de commande (toujours définie). */
export function paymentFacet(statusName: string | null | undefined): StatusFacet {
  if (!statusName) return PAYMENT_FACETS.Pending!;
  return (
    PAYMENT_FACETS[statusName] ?? { label: humanize(statusName), tone: 'neutral', icon: 'ph:info' }
  );
}

/** Facette « livraison », absente tant que la commande n'est pas réglée. */
export function deliveryFacet(statusName: string | null | undefined): StatusFacet | null {
  return (statusName ? DELIVERY_FACETS[statusName] : undefined) ?? null;
}

/** Libellé court d'un statut, pour un titre ou une liste. */
export function orderStatusLabel(statusName: string | null | undefined): string {
  return (deliveryFacet(statusName) ?? paymentFacet(statusName)).label;
}

export const DELIVERY_TYPE_LABELS: Readonly<Record<string, string>> = {
  pickup: 'Retrait en magasin',
  home_delivery: 'Livraison à domicile',
  air_freight: 'Fret aérien',
};

/** `PaymentReview` → « Payment review » : jamais un nom de code brut en vitrine. */
function humanize(code: string): string {
  const spaced = code
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
    .toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
