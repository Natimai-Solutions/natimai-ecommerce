import { Cookies, Dark } from 'quasar';

import { toDarkValue, type ThemePreference } from '@app/ui/theme';

export { parseThemePreference, toDarkValue, type ThemePreference } from '@app/ui/theme';

/** Choix explicite du visiteur (absent = suivre le système). */
export const THEME_COOKIE = 'natimai-theme';
/** Dernier mode résolu dans le navigateur, lu par le rendu serveur. */
export const THEME_HINT_COOKIE = 'natimai-theme-hint';

export const THEME_COOKIE_OPTIONS = {
  path: '/',
  expires: 365,
  sameSite: 'Lax',
} as const;

/** Bascule clair / sombre depuis l'interface (navigateur uniquement). */
export function toggleTheme(): void {
  const next: ThemePreference = Dark.isActive ? 'light' : 'dark';
  Cookies.set(THEME_COOKIE, next, THEME_COOKIE_OPTIONS);
  Dark.set(toDarkValue(next));
}
