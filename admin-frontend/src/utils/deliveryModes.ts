/**
 * Modes de livraison proposés au client (tronçon final, `is_to_customer`).
 *
 * Le code (`last_leg_delivery_type`) est ce que le checkout envoie ; le
 * transport (`mode`) en découle. « Autre » laisse saisir un code libre. Le
 * checkout propose un trajet par code et par destination, sauf pour un
 * retrait : chaque lieu de retrait est une option, le client choisit.
 */
export interface DeliveryPreset {
  value: string;
  mode: string;
  /** Clé de message sous `logistics.` */
  key: string;
}

export const CUSTOM_DELIVERY = '__custom__';

export const DELIVERY_PRESETS: DeliveryPreset[] = [
  { value: 'pickup', mode: 'pickup', key: 'dm_pickup' },
  { value: 'home_delivery', mode: 'road', key: 'dm_home' },
  { value: 'air_freight', mode: 'air', key: 'dm_air' },
  { value: 'sea_freight', mode: 'sea', key: 'dm_sea' },
];

export function presetOf(type: string | null | undefined): DeliveryPreset | undefined {
  return DELIVERY_PRESETS.find((p) => p.value === type);
}

/** Libellé traduit d'un code de mode ; un code personnalisé s'affiche tel quel. */
export function deliveryTypeLabel(type: string, t: (key: string) => string): string {
  const preset = presetOf(type);
  return preset ? t(`logistics.${preset.key}`) : type;
}

export const DELIVERY_CODE_PATTERN = /^[a-z0-9_-]+$/i;
