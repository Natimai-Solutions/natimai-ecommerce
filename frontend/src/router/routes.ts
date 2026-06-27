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
      {
        path: 'connexion',
        name: 'login',
        component: () => import('pages/LoginPage.vue'),
      },
      {
        path: 'inscription',
        name: 'register',
        component: () => import('pages/RegisterPage.vue'),
      },
      {
        path: 'oauth/callback',
        name: 'oauth-callback',
        component: () => import('pages/OAuthCallbackPage.vue'),
      },
      {
        path: 'mon-compte',
        name: 'account',
        component: () => import('pages/MyAccountPage.vue'),
      },
      {
        path: 'mon-compte/commandes/:id',
        name: 'order-tracking',
        component: () => import('pages/OrderTrackingPage.vue'),
      },
      {
        path: 'checkout',
        name: 'checkout',
        component: () => import('pages/CheckoutPage.vue'),
      },
      {
        path: 'paiement/retour',
        name: 'payment-return',
        component: () => import('pages/PaymentReturnPage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
