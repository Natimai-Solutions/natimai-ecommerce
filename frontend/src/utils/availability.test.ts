import { describe, expect, it } from 'vitest';

import { makeTranslate } from '../i18n/translate';
import {
  conditionLabel as conditionLabelIn,
  isRefurbished,
  productAvailability as productAvailabilityIn,
  refurbishedDetails as refurbishedDetailsIn,
  type AvailabilityInput,
  type ConditionInput,
} from './availability';

// The labels are message keys: the historical assertions read the French ones.
const fr = makeTranslate('fr');
const productAvailability = (p: AvailabilityInput) => productAvailabilityIn(p, fr);
const conditionLabel = (p: ConditionInput) => conditionLabelIn(p, fr);
const refurbishedDetails = (p: ConditionInput) => refurbishedDetailsIn(p, fr);

describe('labels in English', () => {
  it('follow the translator', () => {
    const en = makeTranslate('en');
    expect(productAvailabilityIn({ supplier_quantity: '3' }, en).label).toBe('3 in stock');
    expect(conditionLabelIn({ condition: 'refurbished', condition_grade: 'b' }, en)).toBe(
      'Refurbished · Grade B',
    );
  });
});

describe('productAvailability', () => {
  it('keeps the historical behaviour for stock products', () => {
    expect(productAvailability({ supplier_quantity: '3.00' })).toMatchObject({
      orderable: true,
      preorder: false,
      quantity: 3,
      label: '3 en stock',
    });
    expect(
      productAvailability({ supplier_quantity: '0.00', availability_mode: 'stock' }),
    ).toMatchObject({
      orderable: false,
      preorder: false,
      quantity: 0,
      label: 'Indisponible',
    });
  });

  it('accepts pre-orders while the supplier shows stock', () => {
    const onDemand = productAvailability({
      supplier_quantity: '1',
      availability_mode: 'on_demand',
    });
    expect(onDemand.orderable).toBe(true);
    expect(onDemand.preorder).toBe(true);
    expect(onDemand.label).toBe('Sur commande');
    expect(
      productAvailability({ supplier_quantity: '0', availability_mode: 'on_demand' }).orderable,
    ).toBe(false);
  });

  it('always accepts continuous products', () => {
    const continuous = productAvailability({
      supplier_quantity: '0',
      availability_mode: 'continuous',
    });
    expect(continuous).toMatchObject({
      orderable: true,
      preorder: true,
      quantity: 0,
      label: 'Sur commande',
    });
  });

  it('treats a malformed quantity as none', () => {
    expect(productAvailability({ supplier_quantity: 'abc' }).orderable).toBe(false);
  });
});

describe('stock location', () => {
  it('says the units are in our warehouse, with the supplier as a bonus', () => {
    const both = productAvailability({
      supplier_quantity: '4',
      available_quantity: '6',
      stock_local: '2',
      stock_supplier: '4',
    });
    expect(both).toMatchObject({
      orderable: true,
      source: 'local',
      label: 'En stock chez nous (2)',
      note: '+ 4 chez le fournisseur',
      localQuantity: 2,
      supplierQuantity: 4,
    });
    expect(
      productAvailability({
        supplier_quantity: '0',
        available_quantity: '3',
        stock_local: '3',
        stock_supplier: '0',
      }).note,
    ).toBeNull();
  });

  it('warns that supplier-only stock takes longer', () => {
    expect(
      productAvailability({
        supplier_quantity: '5',
        available_quantity: '5',
        stock_local: '0',
        stock_supplier: '5',
      }),
    ).toMatchObject({
      source: 'supplier',
      label: 'En stock chez le fournisseur (5)',
      note: 'Délai de livraison plus long',
    });
  });

  it('keeps the plain label when the response has no split', () => {
    expect(productAvailability({ supplier_quantity: '3' })).toMatchObject({
      source: 'unknown',
      label: '3 en stock',
    });
  });
});

describe('refurbished lots', () => {
  it('counts the units left in the lot and closes it at zero', () => {
    expect(productAvailability({ supplier_quantity: '3', availability_mode: 'lot' })).toMatchObject(
      {
        orderable: true,
        preorder: false,
        quantity: 3,
        label: '3 exemplaires restants sur ce lot',
      },
    );
    expect(productAvailability({ supplier_quantity: '1', availability_mode: 'lot' }).label).toBe(
      '1 exemplaire restant sur ce lot',
    );
    expect(productAvailability({ supplier_quantity: '0', availability_mode: 'lot' })).toMatchObject(
      {
        orderable: false,
        preorder: false,
        quantity: 0,
        label: 'Lot épuisé',
      },
    );
  });

  it('labels the condition and lists the refurbished details', () => {
    expect(conditionLabel({})).toBe('Neuf');
    expect(conditionLabel({ condition: 'new' })).toBe('Neuf');
    expect(conditionLabel({ condition: 'refurbished' })).toBe('Reconditionné');
    expect(conditionLabel({ condition: 'refurbished', condition_grade: 'a' })).toBe(
      'Reconditionné · Grade A',
    );
    expect(isRefurbished({ condition: 'refurbished' })).toBe(true);
    expect(refurbishedDetails({ condition: 'new', warranty_months: 24 })).toMatchObject([]);
    expect(
      refurbishedDetails({
        condition: 'refurbished',
        condition_grade: 'b',
        battery_health_pct: 85,
        os_licence: 'Windows 11 Pro',
        warranty_months: 12,
      }),
    ).toMatchObject([
      { label: 'Grade', value: 'B' },
      { label: 'Batterie', value: '85 %' },
      { label: 'Licence', value: 'Windows 11 Pro' },
      { label: 'Garantie', value: '12 mois' },
    ]);
  });
});
