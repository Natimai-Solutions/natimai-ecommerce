import { watch } from 'vue';
import { defineBoot } from '#q-app';
import { Cookies } from 'quasar';

import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import '@phosphor-icons/web/light';

import { phosphorIconMapFn } from '@/icons/phosphor';
import {
  THEME_COOKIE,
  THEME_HINT_COOKIE,
  THEME_COOKIE_OPTIONS,
  parseThemePreference,
  toDarkValue,
} from '@/utils/theme';

/**
 * Fondations visuelles : polices Geist auto-hébergées, icônes Phosphor et
 * thème clair / sombre.
 *
 * Le choix explicite du visiteur est gardé dans un cookie. Sans choix, la
 * vitrine suit le système (« auto ») ; le dernier mode résolu côté navigateur
 * est mémorisé à part pour que le rendu serveur suivant sorte déjà dans le bon
 * mode, sans flash.
 */
export default defineBoot(({ app, ssrContext }) => {
  const $q = app.config.globalProperties.$q;
  $q.iconMapFn = phosphorIconMapFn;

  const cookies =
    import.meta.env.QUASAR_SERVER && ssrContext ? Cookies.parseSSR(ssrContext) : Cookies;
  const preference = parseThemePreference(cookies.get(THEME_COOKIE));

  if (import.meta.env.QUASAR_SERVER) {
    $q.dark.set(
      preference === 'auto' ? cookies.get(THEME_HINT_COOKIE) === 'dark' : toDarkValue(preference),
    );
    return;
  }

  $q.dark.set(toDarkValue(preference));
  watch(
    () => $q.dark.isActive,
    (isDark) => {
      Cookies.set(THEME_HINT_COOKIE, isDark ? 'dark' : 'light', THEME_COOKIE_OPTIONS);
    },
    { immediate: true },
  );
});
