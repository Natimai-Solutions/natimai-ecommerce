import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      { path: '', component: () => import('@/pages/IndexPage.vue') },
      { path: 'products', component: () => import('@/pages/ProductsPage.vue') },
      { path: 'categories', component: () => import('@/pages/CategoriesPage.vue') },
      { path: 'orders', component: () => import('@/pages/OrdersPage.vue') },
      { path: 'orders/:id', component: () => import('@/pages/OrderDetailPage.vue') },
      {
        path: 'grouped-departures',
        component: () => import('@/pages/GroupedDeparturesPage.vue'),
      },
      { path: 'invoices', component: () => import('@/pages/InvoicesPage.vue') },
      { path: 'credit-notes', component: () => import('@/pages/CreditNotesPage.vue') },
      { path: 'quote-requests', component: () => import('@/pages/QuoteRequestsPage.vue') },
      { path: 'shipping', component: () => import('@/pages/ShippingPage.vue') },
      { path: 'carriers', component: () => import('@/pages/CarriersPage.vue') },
      {
        path: 'logistics-routes',
        component: () => import('@/pages/LogisticsRoutesPage.vue'),
      },
      { path: 'inventory', component: () => import('@/pages/InventoryPage.vue') },
      { path: 'price-groups', component: () => import('@/pages/PriceGroupsPage.vue') },
      { path: 'tax-rates', component: () => import('@/pages/TaxRatesPage.vue') },
      { path: 'customs-rates', component: () => import('@/pages/CustomsRatesPage.vue') },
      { path: 'currency-rates', component: () => import('@/pages/CurrencyRatesPage.vue') },
      { path: 'promotions', component: () => import('@/pages/PromotionsPage.vue') },
      { path: 'discounts', component: () => import('@/pages/DiscountsPage.vue') },
      { path: 'spec-definitions', component: () => import('@/pages/SpecDefinitionsPage.vue') },
      { path: 'supplier-orders', component: () => import('@/pages/SupplierOrdersPage.vue') },
      { path: 'suppliers', component: () => import('@/pages/SuppliersPage.vue') },
      { path: 'system-settings', component: () => import('@/pages/SystemSettingsPage.vue') },
      { path: 'modules', component: () => import('@/pages/ModulesPage.vue') },
      { path: 'security', component: () => import('@/pages/SecurityPage.vue') },
      { path: 'audit-log', component: () => import('@/pages/AuditLogPage.vue') },
      { path: 'pages', component: () => import('@/pages/PagesPage.vue') },
      { path: 'homepage', component: () => import('@/pages/HomepagePage.vue') },
      {
        path: 'group-upgrade-requests',
        component: () => import('@/pages/GroupUpgradeRequestsPage.vue'),
      },
      { path: 'addresses', component: () => import('@/pages/AddressesPage.vue') },
      { path: 'users', component: () => import('@/pages/UsersPage.vue') },
      { path: 'abandoned-carts', component: () => import('@/pages/AbandonedCartsPage.vue') },
      {
        path: 'payment-eligibility',
        component: () => import('@/pages/PaymentEligibilityPage.vue'),
      },
      {
        path: 'payment-validations',
        component: () => import('@/pages/PaymentValidationsPage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('@/pages/ErrorNotFound.vue'),
  },
];

export default routes;
