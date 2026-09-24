<template>
  <!-- fff : le footer défile avec le contenu (non fixé) -->
  <q-layout view="hHh lpR fff">
    <q-header elevated class="bg-white text-dark">
      <q-toolbar>
        <q-btn flat dense round icon="menu" aria-label="Menu" class="lt-md" @click="toggleDrawer" />

        <q-toolbar-title shrink>
          <router-link to="/" class="text-dark text-weight-bold no-underline">
            Natimai
          </router-link>
        </q-toolbar-title>

        <!-- Navigation principale (desktop) -->
        <div class="gt-sm q-ml-md row items-center q-gutter-sm">
          <q-btn
            flat
            dense
            no-caps
            label="Catalogue"
            :to="{ name: 'catalogue' }"
            :class="{ 'text-primary': $route.name === 'catalogue' }"
          />
        </div>

        <q-space />

        <!-- Sélecteur de devise d'affichage (présentationnel ; paiement en XPF) -->
        <q-select
          v-if="currencyStore.available.length > 1"
          :model-value="currencyStore.currency"
          :options="currencyStore.available"
          dense
          borderless
          options-dense
          class="q-mr-sm"
          style="min-width: 64px"
          @update:model-value="onCurrencyChange"
        >
          <template #prepend><q-icon name="payments" size="xs" /></template>
        </q-select>

        <!-- Icône panier -->
        <q-btn flat round icon="shopping_cart" :to="{ name: 'cart' }">
          <q-badge v-if="cartCount > 0" color="primary" floating>
            {{ cartCount }}
          </q-badge>
        </q-btn>

        <!-- Mon compte (connecté uniquement) -->
        <q-btn
          v-if="authStore.isAuthenticated"
          flat
          dense
          no-caps
          icon="person"
          label="Mon compte"
          :to="{ name: 'account' }"
          :class="{ 'text-primary': $route.name === 'account' }"
        />

        <!-- Connexion / déconnexion -->
        <q-btn
          v-if="!authStore.isAuthenticated"
          flat
          dense
          no-caps
          icon="login"
          label="Connexion"
          :to="{ name: 'login' }"
        />
        <q-btn v-else flat dense no-caps icon="logout" label="Déconnexion" @click="onLogout" />
      </q-toolbar>
    </q-header>

    <!-- Drawer mobile -->
    <q-drawer v-model="drawerOpen" bordered overlay>
      <q-list>
        <q-item-label header>Navigation</q-item-label>
        <q-item clickable :to="{ name: 'catalogue' }" @click="drawerOpen = false">
          <q-item-section avatar><q-icon name="grid_view" /></q-item-section>
          <q-item-section>Catalogue</q-item-section>
        </q-item>
        <q-item clickable :to="{ name: 'cart' }" @click="drawerOpen = false">
          <q-item-section avatar><q-icon name="shopping_cart" /></q-item-section>
          <q-item-section>Panier</q-item-section>
          <q-item-section side>
            <q-badge v-if="cartCount > 0" color="primary">{{ cartCount }}</q-badge>
          </q-item-section>
        </q-item>
        <q-item
          v-if="authStore.isAuthenticated"
          clickable
          :to="{ name: 'account' }"
          @click="drawerOpen = false"
        >
          <q-item-section avatar><q-icon name="person" /></q-item-section>
          <q-item-section>Mon compte</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <NextDepartureBanner />
      <router-view />
    </q-page-container>

    <q-footer bordered class="bg-grey-2 text-grey-8">
      <div class="footer-content q-pa-md row items-center justify-between q-col-gutter-sm">
        <div class="col-12 col-sm-auto text-caption">
          © {{ currentYear }} Natimai Solutions — Tous droits réservés
        </div>
        <nav class="col-12 col-sm-auto row q-gutter-md text-caption">
          <router-link :to="{ name: 'cgv' }" class="footer-link">CGV</router-link>
          <router-link :to="{ name: 'mentions-legales' }" class="footer-link">
            Mentions légales
          </router-link>
          <router-link :to="{ name: 'confidentialite' }" class="footer-link">
            Confidentialité &amp; cookies
          </router-link>
        </nav>
      </div>
    </q-footer>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useCartStore } from 'src/stores/cart';
import { useAuthStore } from 'src/stores/auth';
import { useCurrencyStore } from 'src/stores/currency';
import { useDepartureStore } from 'src/stores/departure';
import NextDepartureBanner from 'src/components/NextDepartureBanner.vue';

const drawerOpen = ref(false);
const cartStore = useCartStore();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();
const departureStore = useDepartureStore();
const router = useRouter();
const cartCount = computed(() => cartStore.totalItems);
const currentYear = new Date().getFullYear();

function toggleDrawer() {
  drawerOpen.value = !drawerOpen.value;
}

function onCurrencyChange(code: string) {
  void currencyStore.setCurrency(code);
}

function onLogout() {
  void authStore.logout();
  void router.push({ name: 'catalogue' });
}

onMounted(() => {
  void cartStore.loadCart();
  void currencyStore.loadRates();
  void departureStore.load();
});
</script>

<style scoped lang="scss">
.no-underline {
  text-decoration: none;
}

.footer-content {
  width: min(1200px, 100%);
  margin: 0 auto;
}

.footer-link {
  color: inherit;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
}
</style>
