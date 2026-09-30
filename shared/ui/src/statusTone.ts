export type StatusTone = 'ok' | 'warn' | 'danger' | 'neutral';

/**
 * Ton d'une étiquette d'état à partir des couleurs Quasar encore renvoyées
 * par les tables de statuts (green, teal, orange, negative…). Le bleu, le gris
 * et l'encre (primary) restent neutres : ils ne portent pas d'état.
 */
export function toneOf(color: string | null | undefined): StatusTone {
  if (!color) return 'neutral';
  if (color === 'positive' || /^(green|teal|light-green)(-|$)/.test(color)) return 'ok';
  if (color === 'warning' || /^(orange|deep-orange|amber|yellow)(-|$)/.test(color)) return 'warn';
  if (color === 'negative' || /^(red|pink)(-|$)/.test(color)) return 'danger';
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
