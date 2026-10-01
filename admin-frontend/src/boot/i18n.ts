import { defineBoot } from '#q-app';
import { Lang } from 'quasar';
import langEn from 'quasar/lang/en-GB.js';
import langFr from 'quasar/lang/fr.js';
import { createI18n } from 'vue-i18n';
import { configureFormatting } from '@app/utils';

import { apiLocale } from '@/boot/api';
import messages, { type MessageSchema } from '@/i18n';
import { setGlobalI18n } from '@/i18n/global';
import { initialLocale, type AppLocale } from '@/i18n/locale';

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

/** Language of the back-office (R7 / L2). */
export default defineBoot(({ app }) => {
  const locale = initialLocale();
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
  Lang.set(QUASAR_LANGS[locale]);
  configureFormatting({ locale });
  apiLocale.value = locale;
  document.documentElement.lang = locale;
});
