<template>
  <q-layout view="lHh Lpr lFf">
    <q-page-container>
      <q-page class="row items-center justify-evenly bg-grey-2">
        <q-card class="login-card" flat bordered>
      <q-card-section>
        <div class="text-h6">Admin — Connexion</div>
        <div class="text-caption text-grey-7">Accès réservé au back-office</div>
      </q-card-section>

      <q-card-section>
        <q-form class="q-gutter-md" @submit.prevent="onSubmit">
          <q-input
            v-model="email"
            type="email"
            label="Email"
            outlined
            autocomplete="username"
            :rules="[(v) => !!v || 'Email requis']"
            autofocus
          />
          <q-input
            v-model="password"
            type="password"
            label="Mot de passe"
            outlined
            autocomplete="current-password"
            :rules="[(v) => !!v || 'Mot de passe requis']"
          />

          <q-banner v-if="auth.loginError" class="bg-negative text-white" dense>
            {{ auth.loginError }}
          </q-banner>

          <q-btn
            type="submit"
            color="primary"
            label="Se connecter"
            class="full-width"
            :loading="auth.loggingIn"
          />
        </q-form>
      </q-card-section>
    </q-card>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from 'src/stores/auth'

const email = ref('')
const password = ref('')
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

async function onSubmit() {
  const ok = await auth.login(email.value, password.value)
  if (ok) {
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/products'
    await router.replace(redirect)
  }
}
</script>

<style scoped>
.login-card {
  width: 100%;
  max-width: 380px;
}
</style>
