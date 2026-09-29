export type StatusTone = 'ok' | 'warn' | 'danger' | 'neutral';

/**
 * Ton d'une étiquette d'état à partir des couleurs Quasar encore utilisées
 * par les tables de statuts (green, orange, negative…).
 */
export function toneOf(color: string | null | undefined): StatusTone {
  if (!color) return 'neutral';
  if (color === 'green' || color === 'positive') return 'ok';
  if (color.startsWith('orange') || color === 'warning') return 'warn';
  if (color === 'negative' || color === 'red') return 'danger';
  return 'neutral';
}
