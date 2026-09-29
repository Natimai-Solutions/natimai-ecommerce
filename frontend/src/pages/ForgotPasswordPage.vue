<template>
  <q-page class="flex flex-center q-pa-md">
    <q-card flat bordered style="width: min(420px, 100%)">
      <q-card-section>
        <div class="text-h6">Mot de passe oublié</div>
        <div class="text-body2 text-grey-7 q-mt-xs">
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
        <AppNotice v-if="sentMessage" tone="success" icon="mark_email_read" class="q-mb-md">
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
            dense
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
import AppNotice from 'src/components/AppNotice.vue';
import { ref } from 'vue';
import { requestPasswordReset } from 'src/api/passwordReset';

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
    errorMessage.value = extractError(err) ?? 'Envoi impossible. Veuillez réessayer.';
  } finally {
    submitting.value = false;
  }
}

function extractError(err: unknown): string | null {
  const data = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data;
  return data?.error?.message ?? null;
}
</script>
