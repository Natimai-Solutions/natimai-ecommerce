import { defineBoot } from '#q-app';

import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import '@phosphor-icons/web/light';

import { createPhosphorIconMapFn, warnMissingIcon } from '@app/ui/icons';
import { readThemePreference, toDarkValue } from '@/utils/theme';

/**
 * Fondations visuelles « Précision », communes avec la vitrine : polices Geist
 * auto-hébergées, icônes Phosphor (les noms Material des pages sont traduits)
 * et thème clair / sombre. Sans choix explicite, l'admin suit le système.
 */
export default defineBoot(({ app }) => {
  const $q = app.config.globalProperties.$q;
  $q.iconMapFn = createPhosphorIconMapFn(import.meta.env.QUASAR_DEV ? warnMissingIcon : undefined);
  $q.dark.set(toDarkValue(readThemePreference()));
});
