<template>
  <q-page class="page-container">
    <div class="app-result" aria-live="polite">
      <template v-if="errorMessage">
        <q-icon
          name="ph:warning-circle"
          size="52px"
          class="app-result__icon app-result__icon--danger"
        />
        <h1>Connexion impossible</h1>
        <p>{{ errorMessage }}</p>
        <div class="app-result__actions">
          <q-btn unelevated color="primary" label="Réessayer" :to="{ name: 'login' }" />
        </div>
      </template>
      <template v-else>
        <q-spinner size="44px" class="app-result__icon" />
        <h1>Connexion en cours</h1>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const errorMessage = ref<string | null>(null);

const OAUTH_ERROR_LABELS: Record<string, string> = {
  user_inactive: 'Votre compte est désactivé. Contactez notre équipe.',
  invalid_state: 'La session de connexion a expiré. Veuillez réessayer.',
  provider_error: "Le fournisseur d'identité a renvoyé une erreur.",
  missing_user_info: 'Profil incomplet renvoyé par le fournisseur.',
  missing_code_or_state: 'Réponse de connexion incomplète.',
  server_error: 'Une erreur interne est survenue pendant la connexion.',
};

onMounted(async () => {
  const oauthError = route.query.oauth_error;
  if (typeof oauthError === 'string') {
    errorMessage.value =
      OAUTH_ERROR_LABELS[oauthError] ?? 'La connexion a échoué. Veuillez réessayer.';
    return;
  }

  // The backend already set the HttpOnly refresh cookie during the redirect.
  // Exchange it for an in-memory access token (no token ever travels in the URL).
  const restored = await authStore.tryRestore();
  if (!restored) {
    errorMessage.value = 'La connexion a échoué. Veuillez réessayer.';
    return;
  }

  const target = sessionStorage.getItem('oauth.redirect') ?? '/';
  sessionStorage.removeItem('oauth.redirect');
  await router.replace(target.startsWith('/') ? target : '/');
});
</script>
