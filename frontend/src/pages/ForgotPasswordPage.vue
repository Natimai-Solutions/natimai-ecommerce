<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">Mot de passe oublié</h1>
        <div class="auth-lead q-mt-xs">
          Indiquez votre adresse email : si un compte y est associé, vous recevrez un lien pour
          choisir un nouveau mot de passe.
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
            label="Email"
            autocomplete="email"
            class="q-mb-md"
            :rules="[(v) => !!v || 'Email requis']"
          />
          <q-btn
            type="submit"
            data-testid="forgot-submit"
            color="primary"
            label="Envoyer le lien"
            class="full-width"
            :loading="submitting"
          />
        </q-form>
      </q-card-section>

      <q-card-section class="q-pt-none text-center">
        <q-btn flat no-caps color="primary" label="Retour à la connexion" :to="{ name: 'login' }" />
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { apiErrorMessage } from '@/utils/errors';
import AppNotice from '@app/ui/AppNotice.vue';
import { ref } from 'vue';
import { requestPasswordReset } from '@/api/passwordReset';

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
    errorMessage.value = apiErrorMessage(err) ?? 'Envoi impossible. Veuillez réessayer.';
  } finally {
    submitting.value = false;
  }
}
</script>
