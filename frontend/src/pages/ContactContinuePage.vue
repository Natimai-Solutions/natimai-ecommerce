<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card" data-testid="contact-continue">
      <q-card-section>
        <h1 class="auth-title">{{ $t('contact.continue_title') }}</h1>
        <div v-if="info" class="auth-lead q-mt-xs">
          {{ $t('contact.continue_lead', { number: info.number }) }}
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <div v-if="loading" class="q-pa-md">
          <q-skeleton type="text" />
          <q-skeleton type="text" width="60%" />
        </div>

        <AppNotice v-else-if="invalid" tone="error">
          {{ $t('contact.link_invalid') }}
          <template #action>
            <q-btn
              flat
              no-caps
              color="primary"
              :label="$t('contact.title')"
              :to="{ name: 'contact' }"
            />
          </template>
        </AppNotice>

        <!-- The address already has an account: sign in, then attach. -->
        <template v-else-if="info?.account === 'account'">
          <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
          <p>{{ $t('contact.continue_account', { email: info.email }) }}</p>
          <q-btn
            v-if="!authStore.isAuthenticated"
            unelevated
            no-caps
            color="primary"
            class="full-width"
            :label="$t('contact.sign_in')"
            :to="{ name: 'login', query: { redirect: route.fullPath } }"
            data-testid="contact-continue-login"
          />
          <q-btn
            v-else
            unelevated
            no-caps
            color="primary"
            class="full-width"
            :label="$t('contact.attach')"
            :loading="working"
            data-testid="contact-continue-attach"
            @click="onAttach"
          />
        </template>

        <!-- No account yet: create it with the proven address. -->
        <q-form v-else-if="info" @submit.prevent="onSignup">
          <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
          <q-input
            :model-value="info.email"
            outlined
            stack-label
            readonly
            :label="$t('auth.email')"
            class="q-mb-md"
          />
          <q-input
            v-model="fullName"
            outlined
            stack-label
            autocomplete="name"
            :label="$t('contact.name')"
            class="q-mb-md"
          />
          <q-input
            v-model="password"
            type="password"
            outlined
            stack-label
            autocomplete="new-password"
            :label="$t('contact.password')"
            :hint="$t('contact.password_hint')"
            :rules="[(v: string) => v.length >= 8 || $t('contact.password_hint')]"
            class="q-mb-md"
            data-testid="contact-continue-password"
          />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            class="full-width"
            :label="$t('contact.create_account')"
            :loading="working"
            data-testid="contact-continue-signup"
          />
        </q-form>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import AppNotice from '@app/ui/AppNotice.vue';

import {
  continueSignedIn,
  continueWithSignup,
  getContinueInfo,
  type ContinueInfo,
} from '@/api/messaging';
import { accessToken } from '@/boot/api';
import { usePageMeta } from '@/composables/usePageMeta';
import { useAuthStore } from '@/stores/auth';
import { apiErrorMessage } from '@/utils/errors';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

usePageMeta(() => ({ title: t('contact.continue_title'), noindex: true }));

const token = String(route.params.token ?? '');
const info = ref<ContinueInfo | null>(null);
const loading = ref(true);
const invalid = ref(false);
const working = ref(false);
const error = ref<string | null>(null);
const fullName = ref('');
const password = ref('');

function toMessages(conversationId?: string) {
  void router.replace({
    name: 'account',
    query: { tab: 'messages', ...(conversationId ? { c: conversationId } : {}) },
  });
}

async function onSignup() {
  working.value = true;
  error.value = null;
  try {
    accessToken.value = await continueWithSignup(
      token,
      password.value,
      fullName.value.trim() || null,
    );
    toMessages();
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('contact.failed');
  } finally {
    working.value = false;
  }
}

async function onAttach() {
  working.value = true;
  error.value = null;
  try {
    toMessages(await continueSignedIn(token));
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('contact.failed');
  } finally {
    working.value = false;
  }
}

onMounted(async () => {
  try {
    info.value = await getContinueInfo(token);
    fullName.value = info.value.name ?? '';
  } catch {
    invalid.value = true;
  } finally {
    loading.value = false;
  }
});
</script>
