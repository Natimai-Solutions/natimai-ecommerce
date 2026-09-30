import { defineRouter } from '#q-app';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import routes from './routes';
import { useAuthStore } from '@/stores/auth';
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
    // A screen of a switched-off module: back to the dashboard.
    const module = moduleOfPath(to.path);
    if (module && auth.isAuthenticated) {
      const shopConfig = useShopConfigStore();
      await shopConfig.load();
      if (!shopConfig.moduleOn(module)) return { path: '/' };
    }
    return true;
  });

  return Router;
});
