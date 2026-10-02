<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">{{ $t('auth.forgot_title') }}</h1>
        <div class="auth-lead q-mt-xs">
          {{ $t('auth.forgot_lead') }}
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <!--
          Le backend répond la même chose que l'adresse existe ou non. On
          affiche donc simplement sa réponse, sans laisser entendre qu'un
          compte a été trouvé.
        -->
        <AppNotice v-if="sentMessage" tone="success" icon="ph:envelope-simple-open" class="q-mb-md">
          {{ sentMessage }}
        </AppNotice>

        <AppNotice v-if="errorMessage" tone="error" class="q-mb-md">
          {{ errorMessage }}
        </AppNotice>

        <q-form v-if="!sentMessage" @submit.prevent="onSubmit">
          <q-input
            v-model="email"
            type="email"
            data-testid="forgot-email"
            outlined
            stack-label
            :label="$t('auth.email')"
            autocomplete="email"
            class="q-mb-md"
            :rules="[(v) => !!v || $t('auth.email_required')]"
          />
          <q-btn
            type="submit"
            data-testid="forgot-submit"
            color="primary"
            :label="$t('auth.send_link')"
            class="full-width"
            :loading="submitting"
          />
        </q-form>
      </q-card-section>

      <q-card-section class="q-pt-none text-center">
        <q-btn
          flat
          no-caps
          color="primary"
          :label="$t('auth.back_to_login')"
          :to="{ name: 'login' }"
        />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { usePageMeta } from '@/composables/usePageMeta';
import { useI18n } from 'vue-i18n';
import { apiErrorMessage } from '@/utils/errors';
import AppNotice from '@app/ui/AppNotice.vue';
import { ref } from 'vue';
import { requestPasswordReset } from '@/api/passwordReset';

const { t } = useI18n();

const email = ref('');
const submitting = ref(false);
const sentMessage = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

async function onSubmit() {
  submitting.value = true;
  errorMessage.value = null;
  try {
    sentMessage.value = await requestPasswordReset(email.value.trim().toLowerCase());
  } catch (err) {
    errorMessage.value = apiErrorMessage(err) ?? t('auth.send_failed');
  } finally {
    submitting.value = false;
  }
}

usePageMeta(() => ({ title: t('auth.forgot_title'), noindex: true }));
</script>
