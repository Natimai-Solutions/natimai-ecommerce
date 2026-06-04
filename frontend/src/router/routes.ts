import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', redirect: { name: 'catalogue' } },
      {
        path: 'catalogue',
        name: 'catalogue',
        component: () => import('pages/CataloguePage.vue'),
      },
      {
        path: 'produit/:id/:slug?',
        name: 'product-detail',
        component: () => import('pages/ProductPage.vue'),
      },
      {
        path: 'panier',
        name: 'cart',
        component: () => import('pages/CartPage.vue'),
      },
      {
        path: 'panier/confirmation',
        name: 'cart-quote-confirmation',
        component: () => import('pages/CartQuoteConfirmationPage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
