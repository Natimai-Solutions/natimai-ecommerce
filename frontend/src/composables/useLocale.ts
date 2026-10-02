import { computed } from 'vue';
import { Cookies, Lang } from 'quasar';
import { useI18n } from 'vue-i18n';
import { configureFormatting } from '@app/utils';

import { updateMyPreferences } from '@/api/account';
import { apiLocale } from '@/boot/api';
import { QUASAR_LANGS } from '@/boot/i18n';
import {
  LOCALE_COOKIE,
  LOCALE_COOKIE_OPTIONS,
  LOCALE_LABELS,
  SUPPORTED_LOCALES,
  normalizeLocale,
  type AppLocale,
} from '@/i18n/locale';
import { useAuthStore } from '@/stores/auth';
import { useProductsStore } from '@/stores/products';
import { useShopModulesStore } from '@/stores/shopModules';

/**
 * The visitor's language: read it, offer the others, switch. A switch is
 * remembered in a cookie (read by the next server render) and, for a signed-in
 * customer, in the account preferences (e-mails and documents follow it).
 */
export function useLocale() {
  const { locale } = useI18n({ useScope: 'global' });
  const shop = useShopModulesStore();

  const current = computed(() => normalizeLocale(locale.value) ?? 'fr');
  const available = computed<AppLocale[]>(() => {
    const offered = (shop.config.available_locales ?? [...SUPPORTED_LOCALES])
      .map((code) => normalizeLocale(code))
      .filter((code): code is AppLocale => code !== null);
    return offered.length ? [...new Set(offered)] : [...SUPPORTED_LOCALES];
  });
  const options = computed(() =>
    available.value.map((code) => ({ value: code, label: LOCALE_LABELS[code] })),
  );

  function apply(code: AppLocale): void {
    locale.value = code;
    Lang.set(QUASAR_LANGS[code]);
    configureFormatting({ locale: code });
    apiLocale.value = code;
    if (typeof document !== 'undefined') document.documentElement.lang = code;
    // Category names come from the API in the request's language (R9 / T3).
    void useProductsStore().loadCategories({ force: true });
  }

  async function setLocale(value: string, options: { persist?: boolean } = {}): Promise<void> {
    const code = normalizeLocale(value);
    if (!code) return;
    apply(code);
    Cookies.set(LOCALE_COOKIE, code, LOCALE_COOKIE_OPTIONS);
    if (options.persist === false) return;
    const auth = useAuthStore();
    if (auth.isAuthenticated) {
      try {
        await updateMyPreferences({ locale: code });
      } catch {
        // the cookie keeps the choice on this browser
      }
    }
  }

  /** A signed-in customer's saved language, unless this browser chose one. */
  function adoptPreference(saved: string | null | undefined): void {
    const code = normalizeLocale(saved);
    if (!code || Cookies.has(LOCALE_COOKIE) || code === current.value) return;
    void setLocale(code, { persist: false });
  }

  return { current, available, options, setLocale, adoptPreference };
}
