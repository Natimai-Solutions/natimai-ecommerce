import { describe, expect, it } from 'vitest';

import { parseThemePreference, toDarkValue } from './theme';

describe('parseThemePreference', () => {
  it('keeps an explicit choice', () => {
    expect(parseThemePreference('light')).toBe('light');
    expect(parseThemePreference('dark')).toBe('dark');
    expect(parseThemePreference('auto')).toBe('auto');
  });

  it('falls back to the system for anything else', () => {
    expect(parseThemePreference(undefined)).toBe('auto');
    expect(parseThemePreference(null)).toBe('auto');
    expect(parseThemePreference('purple')).toBe('auto');
    expect(parseThemePreference(42)).toBe('auto');
  });
});

describe('toDarkValue', () => {
  it('maps a preference to what Quasar Dark expects', () => {
    expect(toDarkValue('auto')).toBe('auto');
    expect(toDarkValue('dark')).toBe(true);
    expect(toDarkValue('light')).toBe(false);
  });
});
