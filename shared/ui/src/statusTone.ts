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

/** Icône par défaut d'un ton, pour une étiquette sans icône métier dédiée. */
export const TONE_ICONS: Readonly<Record<StatusTone, string>> = {
  ok: 'ph:check-circle',
  warn: 'ph:clock',
  danger: 'ph:warning-circle',
  neutral: 'ph:circle',
};

export function toneIcon(tone: StatusTone): string {
  return TONE_ICONS[tone];
}
