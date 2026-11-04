import type { HelpItem } from '@/components/HelpPanel.vue';

/**
 * Encarts d'aide partagés par plusieurs écrans : le même parcours, l'étape de
 * l'écran courant marquée « Cet écran ». Textes vérifiés sur le code (prix :
 * product/services/group_pricing.py, discount/services/checkout_discount.py ;
 * paiements : payment/services/manual_payment.py, handlers/payment.py).
 */
type Translate = (key: string) => string;

function steps(t: Translate, prefix: string, keys: string[], current: string): HelpItem[] {
  return keys.map((key) => ({
    title: t(`${prefix}_${key}_title`),
    text: t(`${prefix}_${key}`),
    current: key === current,
  }));
}

/** Ce que paie le client : groupe → promotion → code promo → carte cadeau. */
export type PricingStep = 'group' | 'promotion' | 'coupon' | 'gift_card';
export function pricingHelp(t: Translate, current: PricingStep): HelpItem[] {
  return steps(t, 'help.pricing', ['group', 'promotion', 'coupon', 'gift_card'], current);
}

/** Paiement manuel : moyens → commande → validation → paiement validé. */
export type PaymentStep = 'methods' | 'order' | 'validation' | 'paid';
export function paymentHelp(t: Translate, current: PaymentStep): HelpItem[] {
  return steps(t, 'help.payment', ['methods', 'order', 'validation', 'paid'], current);
}
