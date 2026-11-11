import type { Composer } from 'vue-i18n';
import type { FormatContext } from '@app/utils';

/**
 * What belongs to one server render (audit 2026-11, F1).
 *
 * The storefront kept the API language, the formatting context and the i18n
 * composer in module variables. Under SSR one Node process renders many
 * requests at once, interleaved at every `await`: a French render could send
 * the English `Accept-Language`, format dates in another zone, or translate
 * with another request's composer — and the client then hydrated a mismatch.
 *
 * `src-ssr/middlewares/render.ts` runs each render inside an
 * `AsyncLocalStorage`, published on `globalThis` under {@link REQUEST_SCOPE_KEY}
 * (the SSR middleware and the app are separate bundles: a shared module
 * instance is not guaranteed). The code below reads the current request's
 * scope; in the browser there is none and the module values apply.
 */
export interface RequestScope {
  locale?: string;
  format?: FormatContext;
  composer?: Composer;
}

export const REQUEST_SCOPE_KEY = Symbol.for('natimai.storefront.requestScope');

interface ScopeStorage {
  getStore(): RequestScope | undefined;
}

export function currentRequestScope(): RequestScope | undefined {
  const storage = (globalThis as Record<symbol, ScopeStorage | undefined>)[REQUEST_SCOPE_KEY];
  return storage?.getStore();
}

/** The request's formatting context, created with the defaults on first use. */
export function requestFormatContext(): FormatContext | undefined {
  const scope = currentRequestScope();
  if (!scope) return undefined;
  scope.format ??= { locale: 'fr', timeZone: 'Pacific/Tahiti' };
  return scope.format;
}
