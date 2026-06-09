<template>
  <q-layout view="hHh lpR fFf">
    <q-header elevated>
      <q-toolbar>
        <q-toolbar-title>Admin — Catalogue</q-toolbar-title>
        <q-btn flat dense icon="logout" label="Déconnexion" @click="onLogout" />
      </q-toolbar>
    </q-header>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from 'src/stores/auth'

const auth = useAuthStore()
const router = useRouter()

function onLogout() {
  auth.logout()
  void router.replace('/login')
}
</script>
