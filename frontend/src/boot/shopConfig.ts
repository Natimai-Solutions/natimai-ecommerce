import { defineBoot } from '#q-app';

import { useShopModulesStore } from '@/stores/shopModules';

/**
 * Shop configuration before the first server render.
 *
 * Quasar evaluates a `useMeta` callback once, at component setup, on the
 * server: the icon links of App.vue (the site icon chosen in the back-office,
 * R9 / T9) are therefore only right if `GET /system/config` has already been
 * read when the app is created. A boot file is awaited before that; the
 * layout's own prefetch then finds the store loaded. On the client the
 * server state is hydrated and the layout reloads it on mount.
 */
export default defineBoot(async ({ store, ssrContext }) => {
  if (!(import.meta.env.QUASAR_SERVER && ssrContext)) return;
  await useShopModulesStore(store).load();
});
