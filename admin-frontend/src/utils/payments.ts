/** Libellé lisible d'un code de prestataire de paiement. */
export function providerLabel(code: string | null | undefined): string {
  if (!code) return '—';
  if (code === 'payzen') return 'Carte bancaire';
  if (code === 'paypal') return 'PayPal';
  if (code === 'store_credit') return 'Avoir';
  if (code === 'manual_cash') return 'Espèces';
  if (code.startsWith('document') || code.startsWith('po_')) return 'Bon de commande';
  if (code.includes('check') || code.includes('cheque')) return 'Chèque';
  if (code.includes('transfer') || code.includes('virement')) return 'Virement';
  if (code.startsWith('manual')) return 'Paiement manuel';
  return code;
}
