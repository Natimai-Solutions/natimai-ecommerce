import { Dark } from 'quasar';

import { parseThemePreference, toDarkValue, type ThemePreference } from '@app/ui/theme';

export { parseThemePreference, toDarkValue, type ThemePreference } from '@app/ui/theme';

/** Choix explicite de l'administrateur, gardé dans ce navigateur. */
const STORAGE_KEY = 'natimai-admin-theme';

export function readThemePreference(): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'auto';
  }
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
