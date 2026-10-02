import { describe, expect, it } from 'vitest';

import { providerLabel } from './payments';

describe('providerLabel', () => {
  it('names the known providers', () => {
    expect(providerLabel('payzen')).toBe('Carte bancaire');
    expect(providerLabel('paypal')).toBe('PayPal');
    expect(providerLabel('store_credit')).toBe('Avoir');
    expect(providerLabel('manual_cash')).toBe('Espèces');
  });

  it('reads the manual methods from their code', () => {
    expect(providerLabel('manual_check')).toBe('Chèque');
    expect(providerLabel('manual_cheque_bank')).toBe('Chèque');
    expect(providerLabel('manual_transfer')).toBe('Virement');
    expect(providerLabel('virement_sepa')).toBe('Virement');
    expect(providerLabel('document_upload')).toBe('Bon de commande');
    expect(providerLabel('po_validation')).toBe('Bon de commande');
    expect(providerLabel('manual_other')).toBe('Paiement manuel');
  });

  it('shows a dash for nothing and echoes an unknown code', () => {
    expect(providerLabel(null)).toBe('—');
    expect(providerLabel(undefined)).toBe('—');
    expect(providerLabel('')).toBe('—');
    expect(providerLabel('stripe')).toBe('stripe');
  });
});
