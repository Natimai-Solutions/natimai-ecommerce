import { defineBoot } from '#q-app';
import { Cookies, Lang } from 'quasar';
import langEn from 'quasar/lang/en-GB.js';
import langFr from 'quasar/lang/fr.js';
import { createI18n } from 'vue-i18n';
import { configureFormatting } from '@app/utils';

import { apiLocale } from '@/boot/api';
import messages, { type MessageSchema } from '@/i18n';
import { setGlobalI18n } from '@/i18n/global';
import { LOCALE_COOKIE, resolveLocale, type AppLocale } from '@/i18n/locale';

/* eslint-disable @typescript-eslint/no-empty-object-type */
declare module 'vue-i18n' {
  // French is the master schema: a key missing in English fails the typecheck.
  export interface DefineLocaleMessage extends MessageSchema {}
  export interface DefineDateTimeFormat {}
  export interface DefineNumberFormat {}
}
/* eslint-enable @typescript-eslint/no-empty-object-type */

// Quasar ships the packs with a looser `formatNumber` signature than `Lang.set`
// expects under `exactOptionalPropertyTypes`.
export const QUASAR_LANGS = { fr: langFr, en: langEn } as unknown as Record<
  AppLocale,
  Parameters<typeof Lang.set>[0]
>;

/**
 * Language of the storefront (R7 / L1), chosen before the first render —
 * server-side too, from the cookie then `Accept-Language` — so the HTML sent
 * is already in the visitor's language (no flash, indexable).
 */
export default defineBoot(({ app, ssrContext }) => {
  const server = import.meta.env.QUASAR_SERVER && ssrContext;
  const cookies = server ? Cookies.parseSSR(ssrContext) : Cookies;
  const acceptLanguage = server
    ? ssrContext.req.headers['accept-language']
    : typeof navigator !== 'undefined'
      ? navigator.languages?.join(',') || navigator.language
      : undefined;
  const locale: AppLocale = resolveLocale({
    cookie: cookies.get(LOCALE_COOKIE),
    acceptLanguage,
  });

  const i18n = createI18n<[MessageSchema], AppLocale, false>({
    locale,
    fallbackLocale: 'fr',
    legacy: false,
    messages,
    missingWarn: import.meta.env.DEV,
    fallbackWarn: false,
  });
  app.use(i18n);
  setGlobalI18n(i18n.global as unknown as Parameters<typeof setGlobalI18n>[0]);

  Lang.set(QUASAR_LANGS[locale], server ? ssrContext : undefined);
  configureFormatting({ locale });
  apiLocale.value = locale;
});
