import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('pages/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('layouts/AdminLayout.vue'),
    children: [
      { path: '', redirect: '/products' },
      { path: 'products', component: () => import('pages/ProductsPage.vue') },
      { path: 'tax-rates', component: () => import('pages/TaxRatesPage.vue') },
      { path: 'currency-rates', component: () => import('pages/CurrencyRatesPage.vue') },
      { path: 'spec-definitions', component: () => import('pages/SpecDefinitionsPage.vue') },
      { path: 'supplier-orders', component: () => import('pages/SupplierOrdersPage.vue') },
      { path: 'system-settings', component: () => import('pages/SystemSettingsPage.vue') },
      {
        path: 'group-upgrade-requests',
        component: () => import('pages/GroupUpgradeRequestsPage.vue'),
      },
      {
        path: 'payment-eligibility',
        component: () => import('pages/PaymentEligibilityPage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
]

export default routes
