import { Dark } from 'quasar';

export type ThemePreference = 'light' | 'dark' | 'auto';

/** Choix explicite de l'administrateur, gardé dans ce navigateur. */
const STORAGE_KEY = 'natimai-admin-theme';

export function parseThemePreference(raw: unknown): ThemePreference {
  return raw === 'light' || raw === 'dark' ? raw : 'auto';
}

export function readThemePreference(): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'auto';
  }
}

/** Valeur attendue par `Dark.set()`. */
export function toDarkValue(preference: ThemePreference): boolean | 'auto' {
  if (preference === 'auto') return 'auto';
  return preference === 'dark';
}

/** Applique et mémorise un choix (« auto » suit le système). */
export function setThemePreference(preference: ThemePreference): void {
  try {
    if (preference === 'auto') window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Stockage indisponible (navigation privée) : le choix vaut pour la session.
  }
  Dark.set(toDarkValue(preference));
}
