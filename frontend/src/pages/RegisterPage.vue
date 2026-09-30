<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">Créer un compte</h1>
        <div class="auth-lead">
          Vérifiez votre email avec un code, puis choisissez un mot de passe.
        </div>
      </q-card-section>

      <q-card-section>
        <AppNotice v-if="error" dense tone="error" class="q-mb-md">
          {{ error }}
        </AppNotice>

        <q-stepper v-model="step" flat animated color="primary" header-nav>
          <!-- Step 1 — email -->
          <q-step :name="1" title="Email" icon="ph:envelope-simple" :done="step > 1">
            <q-form @submit.prevent="onSendOtp">
              <q-input
                v-model="email"
                type="email"
                outlined
                stack-label
                label="Email"
                autocomplete="email"
                :rules="[(v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Email invalide']"
              />
              <q-btn
                type="submit"
                color="primary"
                label="Recevoir mon code"
                class="full-width q-mt-md"
                :loading="loading"
              />
            </q-form>

            <template v-if="oauthEnabled">
              <div class="row items-center q-my-md">
                <q-separator class="col" />
                <span class="q-mx-sm auth-or">ou</span>
                <q-separator class="col" />
              </div>
              <q-btn
                outline
                color="primary"
                icon="img:https://www.google.com/favicon.ico"
                label="Continuer avec Google"
                class="full-width q-mb-sm"
                @click="oauthSignup('google')"
              />
              <q-btn
                outline
                color="primary"
                icon="ph:windows-logo"
                label="Continuer avec Microsoft"
                class="full-width"
                @click="oauthSignup('microsoft')"
              />
            </template>
          </q-step>

          <!-- Step 2 — OTP code -->
          <q-step :name="2" title="Code" icon="ph:password" :done="step > 2">
            <div class="auth-lead q-mb-sm">
              Un code à 6 chiffres a été envoyé à <strong>{{ email }}</strong
              >.
            </div>
            <q-form @submit.prevent="onVerifyOtp">
              <q-input
                v-model="code"
                outlined
                stack-label
                label="Code de vérification"
                mask="######"
                inputmode="numeric"
                autofocus
                :rules="[(v) => (v && v.length === 6) || 'Code à 6 chiffres requis']"
              />
              <q-btn
                type="submit"
                color="primary"
                label="Valider le code"
                class="full-width q-mt-md"
                :loading="loading"
              />
            </q-form>
            <q-btn
              flat
              dense
              no-caps
              color="primary"
              label="Renvoyer un code"
              class="q-mt-sm"
              :disable="loading"
              @click="onSendOtp"
            />
          </q-step>

          <!-- Step 3 — password -->
          <q-step :name="3" title="Mot de passe" icon="ph:lock-simple">
            <q-form @submit.prevent="onComplete">
              <q-input
                v-model="fullName"
                outlined
                stack-label
                label="Nom complet (optionnel)"
                autocomplete="name"
                class="q-mb-sm"
              />
              <q-input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                outlined
                stack-label
                label="Mot de passe"
                autocomplete="new-password"
                class="q-mb-sm"
                :rules="[(v) => (v && v.length >= 8) || 'Au moins 8 caractères']"
              >
                <template #append>
                  <q-icon
                    :name="showPassword ? 'ph:eye-slash' : 'ph:eye'"
                    class="cursor-pointer"
                    @click="showPassword = !showPassword"
                  />
                </template>
              </q-input>
              <q-input
                v-model="passwordConfirm"
                :type="showPassword ? 'text' : 'password'"
                outlined
                stack-label
                label="Confirmer le mot de passe"
                autocomplete="new-password"
                :rules="[(v) => v === password || 'Les mots de passe ne correspondent pas']"
              />
              <q-btn
                type="submit"
                color="primary"
                label="Créer mon compte"
                class="full-width q-mt-md"
                :loading="loading"
              />
            </q-form>
          </q-step>
        </q-stepper>
      </q-card-section>

      <q-card-section class="text-center q-pt-none">
        <span class="auth-lead">Déjà un compte ?</span>
        <q-btn flat dense no-caps color="primary" label="Se connecter" :to="{ name: 'login' }" />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import AppNotice from '@app/ui/AppNotice.vue';
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const step = ref(1);
const email = ref('');
const code = ref('');
const fullName = ref('');
const password = ref('');
const passwordConfirm = ref('');
const showPassword = ref(false);
const signupToken = ref('');
const loading = ref(false);
const error = ref<string | null>(null);

const apiUrl = import.meta.env.VITE_API_URL as string | undefined;
const oauthEnabled = Boolean(apiUrl) && import.meta.env.VITE_OAUTH_ENABLED === 'true';

function redirectTarget(): string {
  const target = route.query.redirect;
  return typeof target === 'string' && target.startsWith('/') ? target : '/';
}

async function onSendOtp() {
  loading.value = true;
  error.value = null;
  try {
    const res = await authStore.sendSignupOtp(email.value.trim().toLowerCase());
    if (res.ok) {
      step.value = 2;
    } else {
      error.value = res.error ?? null;
    }
  } finally {
    loading.value = false;
  }
}

async function onVerifyOtp() {
  loading.value = true;
  error.value = null;
  try {
    const res = await authStore.verifySignupOtp(email.value.trim().toLowerCase(), code.value);
    if (res.ok && res.signupToken) {
      signupToken.value = res.signupToken;
      step.value = 3;
    } else {
      error.value = res.error ?? null;
    }
  } finally {
    loading.value = false;
  }
}

async function onComplete() {
  loading.value = true;
  error.value = null;
  try {
    const res = await authStore.completeSignup(
      signupToken.value,
      password.value,
      fullName.value.trim() || null,
    );
    if (res.ok) {
      await router.replace(redirectTarget());
    } else {
      error.value = res.error ?? null;
    }
  } finally {
    loading.value = false;
  }
}

function oauthSignup(provider: 'google' | 'microsoft') {
  if (!apiUrl) return;
  sessionStorage.setItem('oauth.redirect', redirectTarget());
  window.location.href = `${apiUrl}/api/v1/auth/${provider}/login`;
}
</script>
