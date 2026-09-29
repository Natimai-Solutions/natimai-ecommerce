import { describe, expect, it } from 'vitest';

import { parseThemePreference, toDarkValue } from './theme';

describe('parseThemePreference', () => {
  it('garde un choix explicite', () => {
    expect(parseThemePreference('light')).toBe('light');
    expect(parseThemePreference('dark')).toBe('dark');
  });

  it('suit le système par défaut ou si le cookie est invalide', () => {
    expect(parseThemePreference(undefined)).toBe('auto');
    expect(parseThemePreference('purple')).toBe('auto');
  });
});

describe('toDarkValue', () => {
  it('traduit la préférence pour $q.dark.set()', () => {
    expect(toDarkValue('auto')).toBe('auto');
    expect(toDarkValue('dark')).toBe(true);
    expect(toDarkValue('light')).toBe(false);
  });
});
