<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">{{ $t('auth.register_title') }}</h1>
        <div class="auth-lead">
          {{ $t('auth.register_lead') }}
        </div>
      </q-card-section>

      <q-card-section>
        <AppNotice v-if="error" dense tone="error" class="q-mb-md">
          {{ error }}
        </AppNotice>

        <q-stepper v-model="step" flat animated color="primary" header-nav>
          <!-- Step 1 — email -->
          <q-step
            :name="1"
            :title="$t('auth.step_email')"
            icon="ph:envelope-simple"
            :done="step > 1"
          >
            <q-form @submit.prevent="onSendOtp">
              <q-input
                v-model="email"
                type="email"
                outlined
                stack-label
                :label="$t('auth.email')"
                autocomplete="email"
                :rules="[(v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || $t('auth.email_invalid')]"
              />
              <div v-if="captcha.enabled.value" ref="captchaEl" class="q-mt-md" />
              <q-btn
                type="submit"
                color="primary"
                :label="$t('auth.get_code')"
                class="full-width q-mt-md"
                :loading="loading"
                :disable="!captcha.ready.value"
              />
            </q-form>

            <template v-if="oauthEnabled">
              <div class="row items-center q-my-md">
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
                @click="oauthSignup('google')"
              />
              <q-btn
                outline
                color="primary"
                icon="ph:windows-logo"
                :label="$t('auth.with_microsoft')"
                class="full-width"
                @click="oauthSignup('microsoft')"
              />
            </template>
          </q-step>

          <!-- Step 2 — OTP code -->
          <q-step :name="2" :title="$t('auth.step_code')" icon="ph:password" :done="step > 2">
            <div class="auth-lead q-mb-sm">
              <i18n-t keypath="auth.code_sent" tag="span"
                ><template #email
                  ><strong>{{ email }}</strong></template
                ></i18n-t
              >
            </div>
            <q-form @submit.prevent="onVerifyOtp">
              <q-input
                v-model="code"
                outlined
                stack-label
                :label="$t('auth.code_label')"
                mask="######"
                inputmode="numeric"
                autofocus
                :rules="[(v) => (v && v.length === 6) || $t('auth.code_required')]"
              />
              <q-btn
                type="submit"
                color="primary"
                :label="$t('auth.validate_code')"
                class="full-width q-mt-md"
                :loading="loading"
              />
            </q-form>
            <q-btn
              flat
              dense
              no-caps
              color="primary"
              :label="$t('auth.resend_code')"
              class="q-mt-sm"
              :disable="loading"
              @click="onSendOtp"
            />
          </q-step>

          <!-- Step 3 — password -->
          <q-step :name="3" :title="$t('auth.step_password')" icon="ph:lock-simple">
            <q-form @submit.prevent="onComplete">
              <q-input
                v-model="fullName"
                outlined
                stack-label
                :label="$t('auth.full_name')"
                autocomplete="name"
                class="q-mb-sm"
              />
              <q-input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                outlined
                stack-label
                :label="$t('auth.password')"
                autocomplete="new-password"
                class="q-mb-sm"
                :rules="[(v) => (v && v.length >= 8) || $t('auth.min_8')]"
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
                :label="$t('auth.password_confirm')"
                autocomplete="new-password"
                :rules="[(v) => v === password || $t('auth.password_mismatch')]"
              />
              <q-btn
                type="submit"
                color="primary"
                :label="$t('auth.create_my_account')"
                class="full-width q-mt-md"
                :loading="loading"
              />
            </q-form>
          </q-step>
        </q-stepper>
      </q-card-section>

      <q-card-section class="text-center q-pt-none">
        <span class="auth-lead">{{ $t('auth.have_account') }}</span>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          :label="$t('auth.sign_in')"
          :to="{ name: 'login' }"
        />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import AppNotice from '@app/ui/AppNotice.vue';
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { usePageMeta } from '@/composables/usePageMeta';
import { useTurnstile } from '@/composables/useTurnstile';
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

// Captcha of the sign-up code request (R8 / U5), when the shop has one.
const captcha = useTurnstile();
const captchaEl = ref<HTMLElement | null>(null);
const { t, locale } = useI18n({ useScope: 'global' });
usePageMeta(() => ({ title: t('auth.register_title'), noindex: true }));
onMounted(() => void captcha.mount(captchaEl.value, locale.value));
watch(captchaEl, (el) => void captcha.mount(el, locale.value));

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
    const res = await authStore.sendSignupOtp(email.value.trim().toLowerCase(), captcha.headers());
    captcha.reset(); // a Turnstile token is single-use
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
