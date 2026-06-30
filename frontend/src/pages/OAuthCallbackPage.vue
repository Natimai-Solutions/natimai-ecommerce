<template>
  <q-page class="flex flex-center q-pa-md">
    <div class="text-center" style="max-width: 420px">
      <template v-if="errorMessage">
        <q-icon name="error_outline" color="negative" size="3em" class="q-mb-md" />
        <div class="text-h6 q-mb-sm">Connexion impossible</div>
        <div class="text-body2 text-grey-7 q-mb-lg">{{ errorMessage }}</div>
        <q-btn color="primary" label="Réessayer" :to="{ name: 'login' }" />
      </template>
      <template v-else>
        <q-spinner color="primary" size="3em" class="q-mb-md" />
        <div class="text-body2 text-grey-7">Connexion en cours…</div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth';

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
