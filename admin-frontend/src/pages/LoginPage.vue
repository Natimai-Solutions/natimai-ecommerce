<template>
  <q-layout view="lHh Lpr lFf">
    <q-page-container>
      <q-page class="login-page">
        <div class="login-panel">
          <div class="login-brand">
            <span class="login-brand__mark" aria-hidden="true">N</span>
            <span>Administration</span>
          </div>
          <h1 class="login-title">Connexion</h1>
          <p class="login-lead">Accès réservé à l'équipe de la boutique.</p>

          <q-form class="login-form" @submit.prevent="onSubmit">
            <q-input
              v-model="email"
              type="email"
              :readonly="auth.needsSecondFactor"
              label="Adresse e-mail"
              data-testid="admin-login-email"
              outlined
              autocomplete="username"
              :rules="[(v) => !!v || 'Adresse e-mail requise']"
              autofocus
            />
            <q-input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              label="Mot de passe"
              data-testid="admin-login-password"
              outlined
              autocomplete="current-password"
              :rules="[(v) => !!v || 'Mot de passe requis']"
            >
              <template #append>
                <q-btn
                  flat
                  round
                  dense
                  :icon="showPassword ? 'ph:eye-slash' : 'ph:eye'"
                  :aria-label="
                    showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'
                  "
                  @click="showPassword = !showPassword"
                />
              </template>
            </q-input>

            <template v-if="auth.needsSecondFactor">
              <AppNotice tone="info" dense>
                Saisissez le code à 6 chiffres de votre application d'authentification (ou un code
                de secours).
              </AppNotice>
              <q-input
                v-model="totpCode"
                label="Code de vérification"
                data-testid="admin-login-totp"
                outlined
                autofocus
                inputmode="numeric"
                autocomplete="one-time-code"
                :rules="[(v) => !!v || 'Code requis']"
              />
            </template>

            <AppNotice v-if="auth.loginError" tone="error" dense data-testid="admin-login-error">{{
              auth.loginError
            }}</AppNotice>

            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="auth.needsSecondFactor ? 'Vérifier' : 'Se connecter'"
              class="full-width login-submit"
              data-testid="admin-login-submit"
              :loading="auth.loggingIn"
            />
          </q-form>
        </div>
      </q-page>
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';

import AppNotice from '@app/ui/AppNotice.vue';
import { useAuthStore } from '@/stores/auth';

const email = ref('');
const password = ref('');
const showPassword = ref(false);
const totpCode = ref('');
const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

async function onSubmit() {
  const ok = await auth.login(
    email.value,
    password.value,
    auth.needsSecondFactor ? totpCode.value : undefined,
  );
  if (ok) {
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await router.replace(redirect);
  }
}
</script>

<style scoped lang="scss">
.login-page {
  display: grid;
  place-items: center;
  padding: 48px 16px;
  background: var(--n-bg);
}

.login-panel {
  width: 100%;
  max-width: 380px;
}

.login-brand {
  margin-bottom: 32px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  font-weight: 500;
  color: var(--n-ink-2);
}

.login-brand__mark {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--n-ink);
  color: var(--n-on-ink);
  font-weight: 700;
  font-size: 15px;
}

.login-title {
  margin: 0 0 6px;
  font-size: 28px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.login-lead {
  margin: 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

.login-form {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.login-submit {
  margin-top: 8px;
  min-height: 46px;
}
</style>
