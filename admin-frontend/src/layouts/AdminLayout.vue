<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" @click="drawer = !drawer" />
        <q-toolbar-title>Administration</q-toolbar-title>
        <q-btn flat dense icon="logout" label="Déconnexion" @click="onLogout" />
      </q-toolbar>
    </q-header>

    <q-drawer v-model="drawer" show-if-above bordered :width="260">
      <q-scroll-area class="fit">
        <q-list padding>
          <template v-for="section in nav" :key="section.label">
            <q-item-label header class="text-grey-7 text-weight-bold">
              {{ section.label }}
            </q-item-label>
            <q-item
              v-for="link in section.links"
              :key="link.to"
              clickable
              :to="link.to"
              active-class="bg-blue-1 text-primary"
            >
              <q-item-section avatar>
                <q-icon :name="link.icon" />
              </q-item-section>
              <q-item-section>{{ link.label }}</q-item-section>
            </q-item>
          </template>
        </q-list>
      </q-scroll-area>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth';
import { useShopConfigStore } from 'src/stores/shopConfig';

const auth = useAuthStore();
const router = useRouter();
const drawer = ref(true);

interface NavLink {
  label: string;
  icon: string;
  to: string;
}
interface NavSection {
  label: string;
  links: NavLink[];
}

/**
 * Screens that only make sense with suppliers, customs or multi-leg
 * logistics. Hidden in SHOP_MODE=simple; the routes stay reachable by URL.
 */
const FULL_MODE_ONLY = new Set([
  '/spec-definitions',
  '/customs-rates',
  '/currency-rates',
  '/logistics-routes',
  '/suppliers',
  '/supplier-orders',
]);

const allNav: NavSection[] = [
  {
    label: 'Catalogue',
    links: [
      { label: 'Produits', icon: 'inventory_2', to: '/products' },
      { label: 'Catégories', icon: 'category', to: '/categories' },
      { label: 'Catalogue de specs', icon: 'tune', to: '/spec-definitions' },
    ],
  },
  {
    label: 'Tarification',
    links: [
      { label: 'Taux TVA / TGC', icon: 'percent', to: '/tax-rates' },
      { label: 'Douane par catégorie', icon: 'gavel', to: '/customs-rates' },
      { label: 'Taux de change', icon: 'currency_exchange', to: '/currency-rates' },
      { label: 'Codes promo', icon: 'local_offer', to: '/discounts' },
    ],
  },
  {
    label: 'Commandes',
    links: [
      { label: 'Commandes clients', icon: 'receipt_long', to: '/orders' },
      { label: 'Départs groupés', icon: 'event_available', to: '/grouped-departures' },
      { label: 'Factures', icon: 'request_quote', to: '/invoices' },
      { label: 'Avoirs', icon: 'receipt', to: '/credit-notes' },
      { label: 'Demandes de devis', icon: 'request_page', to: '/quote-requests' },
      { label: 'Logistique', icon: 'inventory_2', to: '/shipping' },
      { label: 'Inventaire', icon: 'warehouse', to: '/inventory' },
      { label: 'Trajets & Lieux', icon: 'route', to: '/logistics-routes' },
      { label: 'Transporteurs', icon: 'local_post_office', to: '/carriers' },
      { label: 'Fournisseurs', icon: 'storefront', to: '/suppliers' },
      { label: 'Commandes fournisseurs', icon: 'local_shipping', to: '/supplier-orders' },
    ],
  },
  {
    label: 'Paiements',
    links: [
      { label: 'Validation paiements', icon: 'price_check', to: '/payment-validations' },
      { label: 'Éligibilité paiement', icon: 'payments', to: '/payment-eligibility' },
    ],
  },
  {
    label: 'Clients',
    links: [
      { label: 'Utilisateurs', icon: 'people', to: '/users' },
      { label: 'Demandes de groupe', icon: 'group_add', to: '/group-upgrade-requests' },
      { label: 'Adresses', icon: 'location_on', to: '/addresses' },
      { label: 'Paniers abandonnés', icon: 'remove_shopping_cart', to: '/abandoned-carts' },
    ],
  },
  {
    label: 'Système',
    links: [
      { label: 'Paramètres', icon: 'settings', to: '/system-settings' },
      { label: 'Pages du site', icon: 'article', to: '/pages' },
    ],
  },
];

const shopConfig = useShopConfigStore();
onMounted(() => void shopConfig.load());

const nav = computed<NavSection[]>(() =>
  shopConfig.isSimple
    ? allNav
        .map((section) => ({
          ...section,
          links: section.links.filter((link) => !FULL_MODE_ONLY.has(link.to)),
        }))
        .filter((section) => section.links.length > 0)
    : allNav,
);

function onLogout() {
  void auth.logout();
  void router.replace('/login');
}
</script>
