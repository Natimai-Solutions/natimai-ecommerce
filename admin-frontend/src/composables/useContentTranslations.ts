import { computed, reactive, ref, type Ref } from 'vue';

import { useShopConfigStore } from '@/stores/shopConfig';

/** `{"en": {"name": "…", "_source": "<digest>"}}` as stored by the API (R9 / T3). */
export type Translations = Record<string, Record<string, unknown>>;
/** Per language: `ok`, `stale` (source changed since) or `missing`. */
export type TranslationStatus = Record<string, string>;

/** Deep-enough copy of a translations mapping (one level of language entries). */
export function cloneTranslations(value: unknown): Translations {
  if (!value || typeof value !== 'object') return {};
  const out: Translations = {};
  for (const [lang, entry] of Object.entries(value as Record<string, unknown>)) {
    if (entry && typeof entry === 'object') out[lang] = { ...(entry as Record<string, unknown>) };
  }
  return out;
}

/**
 * One form, several languages: the source texts live in the form's own
 * fields, the translations in `form.translations[lang][field]`. `texts.<field>`
 * reads and writes whichever the selected language is, so an input binds to
 * it once and follows the tabs.
 */
export function useContentTranslations<F extends string>(options: {
  form: Record<F, string> & { translations: Translations };
  fields: readonly F[];
  /** Status computed by the API for the record being edited (none when creating). */
  status?: () => TranslationStatus | undefined | null;
}) {
  const shop = useShopConfigStore();
  const source = computed(() => shop.config?.default_locale ?? 'fr');
  const locales = computed(() => {
    const offered = shop.config?.available_locales ?? ['fr', 'en'];
    return [source.value, ...offered.filter((code) => code !== source.value)];
  });
  const lang: Ref<string> = ref(source.value);
  const isSource = computed(() => lang.value === source.value);

  function entry(create: boolean): Record<string, unknown> | undefined {
    const current = options.form.translations[lang.value];
    if (current || !create) return current;
    options.form.translations[lang.value] = {};
    return options.form.translations[lang.value];
  }

  const texts = reactive(
    Object.fromEntries(
      options.fields.map((field) => [
        field,
        computed<string>({
          get: () => {
            if (isSource.value) return options.form[field];
            const value = entry(false)?.[field];
            return typeof value === 'string' ? value : '';
          },
          set: (value: string) => {
            if (isSource.value) (options.form as Record<F, string>)[field] = value;
            else entry(true)![field] = value;
          },
        }),
      ]),
    ),
  ) as unknown as Record<F, string>;

  /** Status of a language as the API last computed it, `missing` for a new record. */
  function statusOf(code: string): string {
    if (code === source.value) return 'source';
    return options.status?.()?.[code] ?? 'missing';
  }

  /** The translation was read again and is fine: the API refreshes its fingerprint. */
  function markReviewed(): void {
    if (isSource.value) return;
    entry(true)!['_refresh'] = true;
  }
  const reviewed = computed(() => !isSource.value && entry(false)?.['_refresh'] === true);

  function reset(): void {
    lang.value = source.value;
  }

  return { lang, source, locales, isSource, texts, statusOf, markReviewed, reviewed, reset };
}
