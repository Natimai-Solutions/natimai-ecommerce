import { defineRouter } from '#q-app';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import routes from './routes';
import { useAuthStore } from '@/stores/auth';
import { useAccessStore } from '@/stores/access';
import { canOpen, homeOf } from '@/utils/staffAccess';
import { useShopConfigStore } from '@/stores/shopConfig';
import { moduleOfPath } from '@/utils/modules';

export default defineRouter((/* { store, ssrContext } */) => {
  const createHistory = import.meta.env.QUASAR_SERVER
    ? createMemoryHistory
    : import.meta.env.QUASAR_VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory;

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(import.meta.env.QUASAR_VUE_ROUTER_BASE),
  });

  let sessionRestored = false;

  Router.beforeEach(async (to) => {
    const auth = useAuthStore();
    // On first navigation, restore the session from the HttpOnly refresh cookie
    // (the access token lives only in memory and is gone after a reload).
    if (!sessionRestored) {
      sessionRestored = true;
      await auth.tryRestore();
    }
    const isPublic = to.matched.some((r) => r.meta.public);
    if (!isPublic && !auth.isAuthenticated) {
      return { path: '/login', query: { redirect: to.fullPath } };
    }
    if (to.path === '/login' && auth.isAuthenticated) {
      return { path: '/' };
    }
    // A team member reaches the screens of their role only (lot ROLE), and
    // lands on the first one whose module is switched on.
    if (!isPublic && auth.isAuthenticated) {
      const access = useAccessStore();
      const shopConfig = useShopConfigStore();
      const [me] = await Promise.all([access.load(), shopConfig.load()]);
      const isOn = (path: string) => {
        const module = moduleOfPath(path);
        return !module || shopConfig.moduleOn(module);
      };
      const home = homeOf(me, isOn);
      if (!canOpen(me, to.path)) return to.path === home ? true : { path: home };
      // A screen of a switched-off module: back to the person's home.
      if (!isOn(to.path)) return to.path === home ? true : { path: home };
    }
    return true;
  });

  return Router;
});
