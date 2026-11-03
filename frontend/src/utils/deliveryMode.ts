import type { Translate } from './availability';

/**
 * Libellé client d'un mode de livraison (last leg) quand l'admin n'a pas saisi
 * de « libellé client » sur le trajet : les modes prédéfinis sont traduits
 * (`delivery_mode.*`), un code personnalisé est juste rendu lisible.
 */
const KNOWN_MODES = ['pickup', 'home_delivery', 'air_freight', 'sea_freight'] as const;

export function deliveryModeLabel(mode: string, t: Translate): string {
  if ((KNOWN_MODES as readonly string[]).includes(mode)) {
    return t(`delivery_mode.${mode}`);
  }
  return mode.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
