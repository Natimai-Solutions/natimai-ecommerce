import { describe, expect, it } from 'vitest';

import { parseThemePreference, toDarkValue } from './theme';

describe('parseThemePreference', () => {
  it('keeps the two explicit choices and falls back to auto', () => {
    expect(parseThemePreference('light')).toBe('light');
    expect(parseThemePreference('dark')).toBe('dark');
    expect(parseThemePreference('auto')).toBe('auto');
    expect(parseThemePreference(null)).toBe('auto');
    expect(parseThemePreference('blue')).toBe('auto');
    expect(parseThemePreference(42)).toBe('auto');
  });
});

describe('toDarkValue', () => {
  it("turns the preference into Quasar's Dark.set() argument", () => {
    expect(toDarkValue('auto')).toBe('auto');
    expect(toDarkValue('dark')).toBe(true);
    expect(toDarkValue('light')).toBe(false);
  });
});
