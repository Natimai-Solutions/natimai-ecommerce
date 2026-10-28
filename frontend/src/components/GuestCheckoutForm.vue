<template>
  <q-form class="app-panel guest-form" data-testid="guest-form" @submit.prevent="submit">
    <div>
      <h3 class="guest-form__title">{{ $t('guest.title') }}</h3>
      <p class="guest-form__hint">{{ $t('guest.hint') }}</p>
    </div>
    <q-input
      v-model="email"
      type="email"
      autocomplete="email"
      outlined
      dense
      :label="$t('guest.email')"
      :rules="[(v) => /.+@.+\..+/.test(v?.trim() ?? '') || $t('guest.email_rule')]"
      lazy-rules
      data-testid="guest-email"
    />
    <q-input
      v-model="fullName"
      autocomplete="name"
      outlined
      dense
      maxlength="255"
      :label="$t('guest.full_name')"
      :rules="[(v) => !!v?.trim() || $t('guest.required')]"
      lazy-rules
      data-testid="guest-name"
    />
    <q-input
      v-model="phone"
      type="tel"
      autocomplete="tel"
      outlined
      dense
      maxlength="50"
      :label="$t('guest.phone')"
      :hint="$t('guest.phone_hint')"
      data-testid="guest-phone"
    />
    <div v-if="captcha.enabled.value" ref="captchaEl" />
    <AppNotice v-if="known" :tone="known === 'guest' ? 'info' : 'warning'" dense>
      {{ error }}
      <template v-if="known === 'account'" #action>
        <q-btn
          flat
          no-caps
          :label="$t('checkout.login_btn')"
          :to="{ name: 'login', query: { redirect: '/checkout' } }"
        />
      </template>
    </AppNotice>
    <AppNotice v-else-if="error" tone="error" dense>{{ error }}</AppNotice>
    <q-btn
      type="submit"
      unelevated
      no-caps
      color="primary"
      :label="$t('guest.submit')"
      :loading="submitting"
      :disable="!captcha.ready.value"
      data-testid="guest-submit"
    />
    <p class="guest-form__legal">{{ $t('guest.legal') }}</p>
  </q-form>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';

import AppNotice from '@app/ui/AppNotice.vue';
import { useTurnstile } from '@/composables/useTurnstile';
import { useAuthStore } from '@/stores/auth';

/**
 * « Commander sans compte » : e-mail, name and phone open a passwordless
 * account and its session; the checkout page, watching the session, then
 * runs as for any customer (this form is gone by then).
 */

const { locale } = useI18n();
const authStore = useAuthStore();
const captcha = useTurnstile();
const captchaEl = ref<HTMLElement | null>(null);
onMounted(() => void captcha.mount(captchaEl.value, locale.value));
watch(captchaEl, (el) => void captcha.mount(el, locale.value));

const email = ref('');
const fullName = ref('');
const phone = ref('');
const submitting = ref(false);
const error = ref<string | null>(null);
/** The address already has an account: sign in, or the link was e-mailed. */
const known = ref<'account' | 'guest' | null>(null);

async function submit() {
  submitting.value = true;
  error.value = null;
  known.value = null;
  try {
    const result = await authStore.startGuestCheckout(
      {
        email: email.value.trim().toLowerCase(),
        full_name: fullName.value.trim(),
        phone: phone.value.trim() || null,
      },
      captcha.headers(),
    );
    captcha.reset(); // a Turnstile token is single-use
    if (result.ok) return;
    error.value = result.error ?? null;
    known.value = result.reason ?? null;
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped lang="scss">
.guest-form {
  display: grid;
  gap: 4px;
}

.guest-form__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.guest-form__hint,
.guest-form__legal {
  margin: 4px 0 8px;
  font-size: 13px;
  color: var(--n-ink-3);
}

.guest-form__legal {
  margin: 4px 0 0;
}
</style>
