/**
 * Ton d'une étiquette d'état (`StatusTag`) : chaque écran traduit ses propres
 * statuts en ton (`orderStatusTone`, `quoteStatusTone`…), jamais en couleur
 * Quasar. Le bleu, le gris et l'encre ne portent pas d'état : neutre.
 */
export type StatusTone = 'ok' | 'warn' | 'danger' | 'neutral';

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
