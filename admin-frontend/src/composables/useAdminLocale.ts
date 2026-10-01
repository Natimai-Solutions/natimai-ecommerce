import { computed } from 'vue';
import { Lang } from 'quasar';
import { useI18n } from 'vue-i18n';
import { configureFormatting } from '@app/utils';

import { apiLocale } from '@/boot/api';
import { QUASAR_LANGS } from '@/boot/i18n';
import {
  LOCALE_LABELS,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  normalizeLocale,
} from '@/i18n/locale';

/** Read and switch the back-office language (kept in this browser). */
export function useAdminLocale() {
  const { locale } = useI18n({ useScope: 'global' });
  const current = computed(() => normalizeLocale(locale.value) ?? 'fr');
  const options = SUPPORTED_LOCALES.map((code) => ({ value: code, label: LOCALE_LABELS[code] }));

  function setLocale(value: string): void {
    const code = normalizeLocale(value);
    if (!code) return;
    locale.value = code;
    Lang.set(QUASAR_LANGS[code]);
    configureFormatting({ locale: code });
    apiLocale.value = code;
    document.documentElement.lang = code;
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, code);
    } catch {
      // private mode: the choice lasts for this page only
    }
  }

  return { current, options, setLocale };
}
