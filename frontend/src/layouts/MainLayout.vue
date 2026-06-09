<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated class="bg-white text-dark">
      <q-toolbar>
        <q-btn
          flat
          dense
          round
          icon="menu"
          aria-label="Menu"
          class="lt-md"
          @click="toggleDrawer"
        />

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

        <!-- Icône panier -->
        <q-btn flat round icon="shopping_cart" :to="{ name: 'cart' }">
          <q-badge v-if="cartCount > 0" color="primary" floating>
            {{ cartCount }}
          </q-badge>
        </q-btn>

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
        <q-btn
          v-else
          flat
          dense
          no-caps
          icon="logout"
          label="Déconnexion"
          @click="onLogout"
        />
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
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useCartStore } from 'src/stores/cart'
import { useAuthStore } from 'src/stores/auth'

const drawerOpen = ref(false)
const cartStore = useCartStore()
const authStore = useAuthStore()
const router = useRouter()
const cartCount = computed(() => cartStore.totalItems)

function toggleDrawer() {
  drawerOpen.value = !drawerOpen.value
}

function onLogout() {
  authStore.logout()
  void router.push({ name: 'catalogue' })
}

onMounted(() => {
  void cartStore.loadCart()
})
</script>

<style scoped lang="scss">
.no-underline {
  text-decoration: none;
}
</style>
