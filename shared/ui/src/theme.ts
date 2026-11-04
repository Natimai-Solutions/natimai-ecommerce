/**
 * Préférence de thème commune à la vitrine et à l'admin. Chaque application
 * garde son stockage : un cookie côté vitrine (lu par le rendu serveur),
 * le localStorage côté admin (SPA).
 */
export type ThemePreference = 'light' | 'dark' | 'auto';

export function parseThemePreference(raw: unknown): ThemePreference {
  return raw === 'light' || raw === 'dark' ? raw : 'auto';
}

/** Valeur attendue par `Dark.set()` / `$q.dark.set()`. */
export function toDarkValue(preference: ThemePreference): boolean | 'auto' {
  if (preference === 'auto') return 'auto';
  return preference === 'dark';
}
