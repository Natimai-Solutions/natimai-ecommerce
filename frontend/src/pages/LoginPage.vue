<template>
  <q-page class="login-page auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">{{ $t('auth.login_title') }}</h1>
        <div class="auth-lead">{{ $t('auth.login_lead') }}</div>
      </q-card-section>

      <q-card-section>
        <AppNotice v-if="passwordChanged && !authStore.loginError" tone="success" class="q-mb-md">
          {{ $t('auth.password_changed') }}
        </AppNotice>
        <AppNotice v-if="accountDeleted && !authStore.loginError" tone="success" class="q-mb-md">
          {{ $t('auth.account_deleted') }}
        </AppNotice>
        <AppNotice v-if="authStore.loginError" tone="error" class="q-mb-md">
          {{ authStore.loginError }}
        </AppNotice>

        <q-form @submit.prevent="onSubmit">
          <q-input
            v-model="email"
            type="email"
            data-testid="login-email"
            outlined
            stack-label
            :label="$t('auth.email')"
            autocomplete="email"
            class="q-mb-sm"
            :rules="[(v) => !!v || $t('auth.email_required')]"
          />
          <q-input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            data-testid="login-password"
            outlined
            stack-label
            :label="$t('auth.password')"
            autocomplete="current-password"
            class="q-mb-md"
            :rules="[(v) => !!v || $t('auth.password_required')]"
          >
            <template #append>
              <q-icon
                :name="showPassword ? 'ph:eye-slash' : 'ph:eye'"
                class="cursor-pointer"
                @click="showPassword = !showPassword"
              />
            </template>
          </q-input>

          <q-btn
            type="submit"
            data-testid="login-submit"
            color="primary"
            :label="$t('auth.sign_in')"
            class="full-width"
            :loading="authStore.loggingIn"
          />
        </q-form>

        <div class="text-center q-mt-sm">
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            color="primary"
            :label="$t('auth.forgot')"
            :to="{ name: 'forgot-password' }"
          />
        </div>
      </q-card-section>

      <q-card-section v-if="oauthEnabled" class="q-pt-none">
        <div class="row items-center q-my-sm">
          <q-separator class="col" />
          <span class="q-mx-sm auth-or">{{ $t('auth.or') }}</span>
          <q-separator class="col" />
        </div>
        <q-btn
          outline
          color="primary"
          icon="img:https://www.google.com/favicon.ico"
          :label="$t('auth.with_google')"
          class="full-width q-mb-sm"
          @click="oauthLogin('google')"
        />
        <q-btn
          outline
          color="primary"
          icon="ph:windows-logo"
          :label="$t('auth.with_microsoft')"
          class="full-width"
          @click="oauthLogin('microsoft')"
        />
      </q-card-section>

      <q-card-section class="text-center q-pt-none">
        <span class="auth-lead">{{ $t('auth.no_account') }}</span>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          :label="$t('auth.create_account')"
          :to="{ name: 'register' }"
        />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { usePageMeta } from '@/composables/usePageMeta';
import AppNotice from '@app/ui/AppNotice.vue';
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useCartStore } from '@/stores/cart';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const email = ref('');
const password = ref('');
const showPassword = ref(false);
// Arrivée depuis « Profil et sécurité » : toutes les sessions ont été fermées.
const passwordChanged = computed(() => route.query.motif === 'mot-de-passe-change');
const accountDeleted = computed(() => route.query.motif === 'compte-supprime');

// OAuth buttons are gated behind an explicit flag: they only work once the
// backend has GOOGLE/MICROSOFT client credentials AND
// FRONTEND_OAUTH_REDIRECT_URL pointing to /oauth/callback. Enable with
// VITE_OAUTH_ENABLED=true once that config is in place.
const apiUrl = import.meta.env.VITE_API_URL as string | undefined;
const oauthEnabled = Boolean(apiUrl) && import.meta.env.VITE_OAUTH_ENABLED === 'true';

function redirectTarget(): string {
  const target = route.query.redirect;
  return typeof target === 'string' && target.startsWith('/') ? target : '/';
}

async function onSubmit() {
  const ok = await authStore.login(email.value.trim().toLowerCase(), password.value);
  if (ok) {
    await useCartStore().mergeAfterLogin();
    await router.replace(redirectTarget());
  }
}

function oauthLogin(provider: 'google' | 'microsoft') {
  if (!apiUrl) return;
  // Remember where to land after the OAuth round-trip.
  sessionStorage.setItem('oauth.redirect', redirectTarget());
  window.location.href = `${apiUrl}/api/v1/auth/${provider}/login`;
}

const { t: tMeta } = useI18n();
usePageMeta(() => ({ title: tMeta('auth.login_title'), noindex: true }));
</script>
