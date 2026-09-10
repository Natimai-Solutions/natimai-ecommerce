import type { RouteRecordRaw } from 'vue-router';

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
      { path: 'categories', component: () => import('pages/CategoriesPage.vue') },
      { path: 'orders', component: () => import('pages/OrdersPage.vue') },
      { path: 'orders/:id', component: () => import('pages/OrderDetailPage.vue') },
      { path: 'invoices', component: () => import('pages/InvoicesPage.vue') },
      { path: 'credit-notes', component: () => import('pages/CreditNotesPage.vue') },
      { path: 'quote-requests', component: () => import('pages/QuoteRequestsPage.vue') },
      { path: 'shipping', component: () => import('pages/ShippingPage.vue') },
      { path: 'carriers', component: () => import('pages/CarriersPage.vue') },
      {
        path: 'logistics-routes',
        component: () => import('pages/LogisticsRoutesPage.vue'),
      },
      { path: 'inventory', component: () => import('pages/InventoryPage.vue') },
      { path: 'tax-rates', component: () => import('pages/TaxRatesPage.vue') },
      { path: 'customs-rates', component: () => import('pages/CustomsRatesPage.vue') },
      { path: 'currency-rates', component: () => import('pages/CurrencyRatesPage.vue') },
      { path: 'spec-definitions', component: () => import('pages/SpecDefinitionsPage.vue') },
      { path: 'supplier-orders', component: () => import('pages/SupplierOrdersPage.vue') },
      { path: 'suppliers', component: () => import('pages/SuppliersPage.vue') },
      { path: 'system-settings', component: () => import('pages/SystemSettingsPage.vue') },
      {
        path: 'group-upgrade-requests',
        component: () => import('pages/GroupUpgradeRequestsPage.vue'),
      },
      { path: 'addresses', component: () => import('pages/AddressesPage.vue') },
      { path: 'users', component: () => import('pages/UsersPage.vue') },
      {
        path: 'payment-eligibility',
        component: () => import('pages/PaymentEligibilityPage.vue'),
      },
      {
        path: 'payment-validations',
        component: () => import('pages/PaymentValidationsPage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
