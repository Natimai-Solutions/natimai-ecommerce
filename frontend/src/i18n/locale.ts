/**
 * Languages of the storefront (R7 / L1) and how the visitor's is chosen:
 * explicit choice (cookie, set by the language switcher or the account
 * preference) → browser languages (`Accept-Language`, read server-side too so
 * the first render is already in the right language) → the shop's default.
 */

export const SUPPORTED_LOCALES = ['fr', 'en'] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: AppLocale = 'fr';
export const LOCALE_COOKIE = 'locale';
export const LOCALE_COOKIE_OPTIONS = {
  path: '/',
  expires: 365,
  sameSite: 'Lax' as const,
};

export const LOCALE_LABELS: Record<AppLocale, string> = {
  fr: 'Français',
  en: 'English',
};

/** `en-GB`, `EN`, ` fr ` → a supported locale, or null. */
export function normalizeLocale(value: string | null | undefined): AppLocale | null {
  const base = (value ?? '').trim().toLowerCase().split(/[-_]/)[0] ?? '';
  return (SUPPORTED_LOCALES as readonly string[]).includes(base) ? (base as AppLocale) : null;
}

/** First supported language of an `Accept-Language` header (by q-value). */
export function fromAcceptLanguage(header: string | null | undefined): AppLocale | null {
  if (!header) return null;
  const ranked = header
    .split(',')
    .map((part, index) => {
      const [tag, ...params] = part.trim().split(';');
      const q = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
      return { tag: tag ?? '', q: q ? Number(q.slice(2)) : 1, index };
    })
    .filter((entry) => entry.tag && Number.isFinite(entry.q) && entry.q > 0)
    .sort((a, b) => b.q - a.q || a.index - b.index);
  for (const entry of ranked) {
    const locale = normalizeLocale(entry.tag);
    if (locale) return locale;
  }
  return null;
}

export function resolveLocale(options: {
  cookie?: string | null | undefined;
  acceptLanguage?: string | null | undefined;
  fallback?: string | null | undefined;
}): AppLocale {
  return (
    normalizeLocale(options.cookie) ??
    fromAcceptLanguage(options.acceptLanguage) ??
    normalizeLocale(options.fallback) ??
    DEFAULT_LOCALE
  );
}
