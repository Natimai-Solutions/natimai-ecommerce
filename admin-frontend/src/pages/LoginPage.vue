<template>
  <q-layout view="lHh Lpr lFf">
    <q-page-container>
      <q-page class="login-page">
        <div class="login-panel">
          <div class="login-brand">
            <span class="login-brand__mark" aria-hidden="true">N</span>
            <span>{{ $t('login.administration') }}</span>
          </div>
          <h1 class="login-title">{{ $t('login.title') }}</h1>
          <p class="login-lead">{{ $t('login.lead') }}</p>
          <AppNotice v-if="route.query.password_changed" tone="success" dense class="q-mb-md">
            {{ $t('login.password_changed') }}
          </AppNotice>

          <q-form class="login-form" @submit.prevent="onSubmit">
            <q-input
              v-model="email"
              type="email"
              :readonly="auth.needsSecondFactor"
              :label="$t('login.email')"
              data-testid="admin-login-email"
              outlined
              autocomplete="username"
              :rules="[(v) => !!v || $t('login.email_required')]"
              autofocus
            />
            <q-input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              :label="$t('login.password')"
              data-testid="admin-login-password"
              outlined
              autocomplete="current-password"
              :rules="[(v) => !!v || $t('login.password_required')]"
            >
              <template #append>
                <q-btn
                  flat
                  round
                  dense
                  :icon="showPassword ? 'ph:eye-slash' : 'ph:eye'"
                  :aria-label="showPassword ? $t('login.hide_password') : $t('login.show_password')"
                  @click="showPassword = !showPassword"
                />
              </template>
            </q-input>

            <template v-if="auth.needsSecondFactor">
              <AppNotice tone="info" dense>
                {{ $t('login.totp_hint') }}
              </AppNotice>
              <q-input
                v-model="totpCode"
                :label="$t('login.code')"
                data-testid="admin-login-totp"
                outlined
                autofocus
                inputmode="numeric"
                autocomplete="one-time-code"
                :rules="[(v) => !!v || $t('login.code_required')]"
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
              :label="auth.needsSecondFactor ? $t('login.verify') : $t('login.sign_in')"
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
  border-radius: var(--n-radius);
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
