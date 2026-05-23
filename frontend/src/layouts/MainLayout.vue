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

        <!-- Barre de recherche rapide (desktop) -->
        <q-input
          v-model="quickSearch"
          dense
          outlined
          rounded
          placeholder="Rechercher…"
          class="gt-sm quick-search-input"
          @keyup.enter="goToSearch"
        >
          <template #append>
            <q-icon name="search" class="cursor-pointer" @click="goToSearch" />
          </template>
        </q-input>

        <q-space />

        <!-- Icône panier -->
        <q-btn flat round icon="shopping_cart" :to="{ name: 'cart' }">
          <q-badge v-if="cartCount > 0" color="primary" floating>
            {{ cartCount }}
          </q-badge>
        </q-btn>
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
      </q-list>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const drawerOpen = ref(false)
const quickSearch = ref('')
const cartCount = ref(0) // TODO: brancher sur le store panier

function toggleDrawer() {
  drawerOpen.value = !drawerOpen.value
}

function goToSearch() {
  if (!quickSearch.value.trim()) return
  void router.push({ name: 'catalogue', query: { q: quickSearch.value.trim() } })
  quickSearch.value = ''
}
</script>

<style scoped lang="scss">
.no-underline {
  text-decoration: none;
}
.quick-search-input {
  max-width: 320px;
}
</style>
