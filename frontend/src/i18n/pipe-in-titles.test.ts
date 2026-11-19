import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

import en from './en';
import fr from './fr';

describe('page titles keep the shop name', () => {
  it('a literal pipe is not a plural separator', () => {
    // « {name} | {shop} » was read as two plural forms: the title showed
    // the product name only, never the shop's.
    for (const [locale, messages] of [
      ['fr', fr],
      ['en', en],
    ] as const) {
      const i18n = createI18n({ legacy: false, locale, messages: { [locale]: messages } });
      const t = i18n.global.t as (key: string, values?: Record<string, unknown>) => string;
      expect(t('product.meta_title', { name: 'Écran', shop: 'Natimai' })).toBe('Écran | Natimai');
      expect(t('catalogue.meta_title', { shop: 'Natimai' })).toContain('| Natimai');
      expect(t('account.meta', { section: 'Profil' })).toContain('Profil |');
    }
  });
});
