import { defineRouter } from '#q-app/wrappers'
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router'
import routes from './routes'
import { useAuthStore } from 'src/stores/auth'

export default defineRouter((/* { store, ssrContext } */) => {
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : process.env.VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(process.env.VUE_ROUTER_BASE),
  })

  Router.beforeEach((to) => {
    const auth = useAuthStore()
    const isPublic = to.matched.some((r) => r.meta.public)
    if (!isPublic && !auth.isAuthenticated) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
    if (to.path === '/login' && auth.isAuthenticated) {
      return { path: '/products' }
    }
    return true
  })

  return Router
})
