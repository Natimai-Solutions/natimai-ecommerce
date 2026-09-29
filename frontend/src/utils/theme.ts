import { Cookies, Dark } from 'quasar';

export type ThemePreference = 'light' | 'dark' | 'auto';

/** Choix explicite du visiteur (absent = suivre le système). */
export const THEME_COOKIE = 'natimai-theme';
/** Dernier mode résolu dans le navigateur, lu par le rendu serveur. */
export const THEME_HINT_COOKIE = 'natimai-theme-hint';

export const THEME_COOKIE_OPTIONS = {
  path: '/',
  expires: 365,
  sameSite: 'Lax',
} as const;

export function parseThemePreference(raw: unknown): ThemePreference {
  return raw === 'light' || raw === 'dark' ? raw : 'auto';
}

/** Valeur attendue par `$q.dark.set()`. */
export function toDarkValue(preference: ThemePreference): boolean | 'auto' {
  if (preference === 'auto') return 'auto';
  return preference === 'dark';
}

/** Bascule clair / sombre depuis l'interface (navigateur uniquement). */
export function toggleTheme(): void {
  const next: ThemePreference = Dark.isActive ? 'light' : 'dark';
  Cookies.set(THEME_COOKIE, next, THEME_COOKIE_OPTIONS);
  Dark.set(toDarkValue(next));
}
