/**
 * Languages of the back-office (R7 / L2): the administrator's choice (kept in
 * this browser), else the browser's languages, else French.
 */

export const SUPPORTED_LOCALES = ['fr', 'en'] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const LOCALE_STORAGE_KEY = 'admin.locale';

export const LOCALE_LABELS: Record<AppLocale, string> = {
  fr: 'Français',
  en: 'English',
};

export function normalizeLocale(value: string | null | undefined): AppLocale | null {
  const base = (value ?? '').trim().toLowerCase().split(/[-_]/)[0] ?? '';
  return (SUPPORTED_LOCALES as readonly string[]).includes(base) ? (base as AppLocale) : null;
}

export function storedLocale(): AppLocale | null {
  try {
    return normalizeLocale(localStorage.getItem(LOCALE_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function initialLocale(): AppLocale {
  const stored = storedLocale();
  if (stored) return stored;
  const browser =
    typeof navigator !== 'undefined' ? [...(navigator.languages ?? []), navigator.language] : [];
  for (const tag of browser) {
    const code = normalizeLocale(tag);
    if (code) return code;
  }
  return 'fr';
}
