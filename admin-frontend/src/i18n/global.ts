import type { Composer } from 'vue-i18n';

/**
 * The app's i18n, for code outside components (stores, plain helpers).
 * Set by the i18n boot; until then keys are returned as is.
 */
let composer: Composer | null = null;

export function setGlobalI18n(value: Composer): void {
  composer = value;
}

/** The interface language right now (`fr` until the i18n boot ran). */
export function currentLocale(): string {
  const value = composer?.locale as unknown;
  if (typeof value === 'string') return value;
  const ref = value as { value?: unknown } | undefined;
  return typeof ref?.value === 'string' ? ref.value : 'fr';
}

export function gt(key: string, named: Record<string, unknown> = {}): string {
  return composer ? composer.t(key, named) : key;
}

/**
 * A label map whose values are message keys, read in the current language
 * at each access (``MAP[code]``, ``Object.entries(MAP)`` keep working).
 */
export function labels<K extends string>(keys: Record<K, string>): Record<K, string> {
  const out = {} as Record<K, string>;
  for (const [code, key] of Object.entries(keys) as [K, string][]) {
    Object.defineProperty(out, code, { enumerable: true, get: () => gt(key) });
  }
  return out;
}
