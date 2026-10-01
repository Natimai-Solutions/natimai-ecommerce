import type { Composer } from 'vue-i18n';

/**
 * The app's i18n, for code outside components (stores, plain helpers).
 * Set by the i18n boot; until then keys are returned as is.
 */
let composer: Composer | null = null;

export function setGlobalI18n(value: Composer): void {
  composer = value;
}

export function gt(key: string, named: Record<string, unknown> = {}): string {
  return composer ? composer.t(key, named) : key;
}
