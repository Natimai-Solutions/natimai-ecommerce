import type { Composer } from 'vue-i18n';

import { currentRequestScope } from '@/ssr/requestScope';

/**
 * The app's i18n, for code outside components (stores' fallback messages).
 * Set by the i18n boot; until then (or in unit tests) keys are returned as is.
 */
let composer: Composer | null = null;

export function setGlobalI18n(value: Composer): void {
  composer = value;
}

/** The interface language right now (`fr` until the i18n boot ran). */
export function currentLocale(): string {
  const active = currentRequestScope()?.composer ?? composer;
  const value = active?.locale as unknown;
  if (typeof value === 'string') return value;
  const ref = value as { value?: unknown } | undefined;
  return typeof ref?.value === 'string' ? ref.value : 'fr';
}

export function gt(key: string, named: Record<string, unknown> = {}): string {
  // Server render: the composer of this request (F1), not the last created.
  const active = currentRequestScope()?.composer ?? composer;
  return active ? active.t(key, named) : key;
}
