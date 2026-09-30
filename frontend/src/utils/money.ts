import { formatMoney } from '@app/utils';

/**
 * Montant « qui fait foi » (commande, facture, solde) dans la devise figée sur
 * la commande, jamais dans la devise d'affichage choisie par le visiteur.
 * Les commandes antérieures à la colonne `currency` retombent sur la devise
 * de référence de la boutique.
 */
export function orderMoney(
  raw: string | number | null | undefined,
  currency: string | null | undefined,
  referenceCurrency = 'XPF',
): string {
  const value = typeof raw === 'number' ? raw : Number.parseFloat(raw ?? '');
  return formatMoney(Number.isFinite(value) ? value : Number.NaN, currency || referenceCurrency);
}

/** Vrai si le montant décimal renvoyé par l'API est strictement positif. */
export function isPositiveAmount(raw: string | number | null | undefined): boolean {
  const value = typeof raw === 'number' ? raw : Number.parseFloat(raw ?? '');
  return Number.isFinite(value) && value > 0;
}
