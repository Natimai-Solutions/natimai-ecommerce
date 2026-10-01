import { describe, expect, it } from 'vitest';

import { makeTranslate } from '../i18n/translate';
import {
  deliveryFacet as deliveryFacetIn,
  orderStatusLabel as orderStatusLabelIn,
  paymentFacet as paymentFacetIn,
} from './orderStatus';

const fr = makeTranslate('fr');
const paymentFacet = (s: string | null | undefined) => paymentFacetIn(s, fr);
const deliveryFacet = (s: string | null | undefined) => deliveryFacetIn(s, fr);
const orderStatusLabel = (s: string | null | undefined) => orderStatusLabelIn(s, fr);

describe('paymentFacet', () => {
  it('traduit tous les statuts de paiement du backend', () => {
    for (const name of [
      'Pending',
      'AwaitingPayment',
      'Paid',
      'DepositPaid',
      'PaymentFailed',
      'PaymentReview',
      'Refunded',
      'PartiallyRefunded',
    ]) {
      expect(paymentFacet(name).label).not.toBe(name);
    }
    expect(paymentFacet('PaymentReview')).toMatchObject({
      label: 'Paiement en vérification',
      tone: 'warn',
    });
  });

  it("n'affiche jamais un code brut pour un statut inconnu", () => {
    expect(paymentFacet('SomethingNew').label).toBe('Something new');
    expect(paymentFacet(null).label).toBe('Paiement en attente');
  });

  it("considère la commande payée dès l'acheminement", () => {
    expect(paymentFacet('InTransit').tone).toBe('ok');
  });
});

describe('deliveryFacet', () => {
  it("n'existe pas avant le paiement", () => {
    expect(deliveryFacet('AwaitingPayment')).toBeNull();
    expect(deliveryFacet(null)).toBeNull();
  });

  it("suit l'acheminement", () => {
    expect(deliveryFacet('AtCustoms')?.label).toBe('En douane');
    expect(deliveryFacet('Delivered')?.tone).toBe('ok');
  });
});

describe('orderStatusLabel', () => {
  it('préfère la facette livraison quand elle existe', () => {
    expect(orderStatusLabel('InTransit')).toBe('En transit');
    expect(orderStatusLabel('AwaitingPayment')).toBe('En attente de paiement');
  });
});
