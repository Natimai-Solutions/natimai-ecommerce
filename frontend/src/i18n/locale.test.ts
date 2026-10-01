import { describe, expect, it } from 'vitest';
import { fromAcceptLanguage, normalizeLocale, resolveLocale } from './locale';

describe('locale resolution', () => {
  it('normalizes tags', () => {
    expect(normalizeLocale('en-GB')).toBe('en');
    expect(normalizeLocale(' FR ')).toBe('fr');
    expect(normalizeLocale('de')).toBeNull();
  });

  it('reads Accept-Language by preference', () => {
    expect(fromAcceptLanguage('de-DE,de;q=0.9,en;q=0.8,fr;q=0.7')).toBe('en');
    expect(fromAcceptLanguage('fr-PF,fr;q=0.9')).toBe('fr');
    expect(fromAcceptLanguage('es;q=1, fr;q=0')).toBeNull();
  });

  it('prefers the explicit choice, then the browser, then the shop', () => {
    expect(resolveLocale({ cookie: 'en', acceptLanguage: 'fr' })).toBe('en');
    expect(resolveLocale({ cookie: 'xx', acceptLanguage: 'en-US' })).toBe('en');
    expect(resolveLocale({ acceptLanguage: 'de', fallback: 'en' })).toBe('en');
    expect(resolveLocale({})).toBe('fr');
  });
});
