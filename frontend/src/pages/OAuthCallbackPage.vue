<template>
  <q-page class="page-container">
    <div class="app-result" aria-live="polite">
      <template v-if="errorMessage">
        <q-icon
          name="ph:warning-circle"
          size="52px"
          class="app-result__icon app-result__icon--danger"
        />
        <h1>{{ $t('oauth.failed_title') }}</h1>
        <p>{{ errorMessage }}</p>
        <div class="app-result__actions">
          <q-btn unelevated color="primary" :label="$t('oauth.retry')" :to="{ name: 'login' }" />
        </div>
      </template>
      <template v-else>
        <q-spinner size="44px" class="app-result__icon" />
        <h1>{{ $t('oauth.in_progress') }}</h1>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { usePageMeta } from '@/composables/usePageMeta';
import { useI18n } from 'vue-i18n';
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const { t } = useI18n();

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const errorMessage = ref<string | null>(null);

const OAUTH_ERRORS = new Set([
  'user_inactive',
  'invalid_state',
  'provider_error',
  'missing_user_info',
  'missing_code_or_state',
  'server_error',
  'email_not_verified',
  'account_exists',
  'superuser_oauth_disabled',
]);

onMounted(async () => {
  const oauthError = route.query.oauth_error;
  if (typeof oauthError === 'string') {
    errorMessage.value = OAUTH_ERRORS.has(oauthError)
      ? t(`oauth.${oauthError}`)
      : t('oauth.failed');
    return;
  }

  // The backend already set the HttpOnly refresh cookie during the redirect.
  // Exchange it for an in-memory access token (no token ever travels in the URL).
  const restored = await authStore.tryRestore();
  if (!restored) {
    errorMessage.value = t('oauth.failed');
    return;
  }

  const target = sessionStorage.getItem('oauth.redirect') ?? '/';
  sessionStorage.removeItem('oauth.redirect');
  await router.replace(target.startsWith('/') ? target : '/');
});

usePageMeta(() => ({ title: t('oauth.in_progress'), noindex: true }));
</script>
