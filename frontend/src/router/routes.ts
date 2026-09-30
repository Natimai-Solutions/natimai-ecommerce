import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/pages/IndexPage.vue'),
      },
      {
        path: 'catalogue',
        name: 'catalogue',
        component: () => import('@/pages/CataloguePage.vue'),
      },
      {
        path: 'produit/:id/:slug?',
        name: 'product-detail',
        component: () => import('@/pages/ProductPage.vue'),
      },
      {
        path: 'panier',
        name: 'cart',
        component: () => import('@/pages/CartPage.vue'),
      },
      {
        path: 'panier/confirmation',
        name: 'cart-quote-confirmation',
        component: () => import('@/pages/CartQuoteConfirmationPage.vue'),
      },
      {
        path: 'connexion',
        name: 'login',
        component: () => import('@/pages/LoginPage.vue'),
      },
      {
        path: 'inscription',
        name: 'register',
        component: () => import('@/pages/RegisterPage.vue'),
      },
      {
        path: 'oauth/callback',
        name: 'oauth-callback',
        component: () => import('@/pages/OAuthCallbackPage.vue'),
      },
      {
        path: 'mon-compte',
        name: 'account',
        component: () => import('@/pages/MyAccountPage.vue'),
      },
      {
        path: 'mon-compte/commandes/:id',
        name: 'order-tracking',
        component: () => import('@/pages/OrderTrackingPage.vue'),
      },
      {
        // Suivi sans compte, depuis le lien signé des e-mails (?t=…).
        path: 'suivi/:id',
        name: 'order-tracking-link',
        component: () => import('@/pages/OrderTrackingPage.vue'),
      },
      {
        // Règlement du solde d'une commande passée avec acompte.
        path: 'mon-compte/commandes/:id/solde',
        name: 'order-balance',
        component: () => import('@/pages/BalancePaymentPage.vue'),
      },
      {
        path: 'checkout',
        name: 'checkout',
        component: () => import('@/pages/CheckoutPage.vue'),
      },
      {
        path: 'paiement/retour',
        name: 'payment-return',
        component: () => import('@/pages/PaymentReturnPage.vue'),
      },
      {
        path: 'mot-de-passe-oublie',
        name: 'forgot-password',
        component: () => import('@/pages/ForgotPasswordPage.vue'),
      },
      {
        // Cible du lien envoyé par email ; le jeton est en query string.
        path: 'reinitialiser',
        name: 'reset-password',
        component: () => import('@/pages/ResetPasswordPage.vue'),
      },
      {
        path: 'comment-ca-marche',
        name: 'how-it-works',
        component: () => import('@/pages/HowItWorksPage.vue'),
      },
      {
        path: 'cgv',
        name: 'cgv',
        component: () => import('@/pages/legal/CgvPage.vue'),
      },
      {
        path: 'mentions-legales',
        name: 'mentions-legales',
        component: () => import('@/pages/legal/MentionsLegalesPage.vue'),
      },
      {
        path: 'confidentialite',
        name: 'confidentialite',
        component: () => import('@/pages/legal/ConfidentialitePage.vue'),
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('@/pages/ErrorNotFound.vue'),
  },
];

export default routes;
