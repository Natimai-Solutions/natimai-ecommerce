<template>
  <q-page class="login-page flex flex-center q-pa-md">
    <q-card flat bordered style="width: 100%; max-width: 420px">
      <q-card-section>
        <div class="text-h5 q-mb-xs">Connexion</div>
        <div class="text-body2 text-grey-7">Connectez-vous pour accéder à votre compte.</div>
      </q-card-section>

      <q-card-section>
        <AppNotice v-if="authStore.loginError" tone="error" class="q-mb-md">
          {{ authStore.loginError }}
        </AppNotice>

        <q-form @submit.prevent="onSubmit">
          <q-input
            v-model="email"
            type="email"
            data-testid="login-email"
            outlined
            dense
            label="Email"
            autocomplete="email"
            class="q-mb-sm"
            :rules="[(v) => !!v || 'Email requis']"
          />
          <q-input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            data-testid="login-password"
            outlined
            dense
            label="Mot de passe"
            autocomplete="current-password"
            class="q-mb-md"
            :rules="[(v) => !!v || 'Mot de passe requis']"
          >
            <template #append>
              <q-icon
                :name="showPassword ? 'visibility_off' : 'visibility'"
                class="cursor-pointer"
                @click="showPassword = !showPassword"
              />
            </template>
          </q-input>

          <q-btn
            type="submit"
            data-testid="login-submit"
            color="primary"
            label="Se connecter"
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
            color="grey-7"
            label="Mot de passe oublié ?"
            :to="{ name: 'forgot-password' }"
          />
        </div>
      </q-card-section>

      <q-card-section v-if="oauthEnabled" class="q-pt-none">
        <div class="row items-center q-my-sm">
          <q-separator class="col" />
          <span class="q-mx-sm text-caption text-grey-6">ou</span>
          <q-separator class="col" />
        </div>
        <q-btn
          outline
          color="grey-8"
          icon="img:https://www.google.com/favicon.ico"
          label="Continuer avec Google"
          class="full-width q-mb-sm"
          @click="oauthLogin('google')"
        />
        <q-btn
          outline
          color="grey-8"
          icon="window"
          label="Continuer avec Microsoft"
          class="full-width"
          @click="oauthLogin('microsoft')"
        />
      </q-card-section>

      <q-card-section class="text-center q-pt-none">
        <span class="text-body2 text-grey-7">Pas encore de compte ?</span>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          label="Créer un compte"
          :to="{ name: 'register' }"
        />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import AppNotice from 'src/components/AppNotice.vue';
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const email = ref('');
const password = ref('');
const showPassword = ref(false);

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
    await router.replace(redirectTarget());
  }
}

function oauthLogin(provider: 'google' | 'microsoft') {
  if (!apiUrl) return;
  // Remember where to land after the OAuth round-trip.
  sessionStorage.setItem('oauth.redirect', redirectTarget());
  window.location.href = `${apiUrl}/api/v1/auth/${provider}/login`;
}
</script>
