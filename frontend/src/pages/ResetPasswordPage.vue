<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">
          {{ invitation ? 'Activez votre compte' : 'Nouveau mot de passe' }}
        </h1>
        <div v-if="invitation" class="text-body2 text-grey-8 q-mt-xs">
          Un compte a été créé pour vous. Choisissez votre mot de passe pour l'ouvrir.
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <AppNotice v-if="!token" tone="error">
          Ce lien est incomplet. Demandez-en un nouveau depuis la page « mot de passe oublié ».
        </AppNotice>

        <template v-else-if="doneMessage">
          <AppNotice tone="success" class="q-mb-md">
            {{ doneMessage }}
          </AppNotice>
          <q-btn color="primary" label="Se connecter" class="full-width" :to="{ name: 'login' }" />
        </template>

        <template v-else>
          <AppNotice v-if="errorMessage" tone="error" class="q-mb-md">
            {{ errorMessage }}
          </AppNotice>

          <q-form @submit.prevent="onSubmit">
            <q-input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              data-testid="reset-password"
              outlined
              stack-label
              label="Nouveau mot de passe"
              autocomplete="new-password"
              class="q-mb-sm"
              :rules="[
                (v) => !!v || 'Mot de passe requis',
                (v) => v.length >= 8 || '8 caractères minimum',
              ]"
            >
              <template #append>
                <q-icon
                  :name="showPassword ? 'visibility_off' : 'visibility'"
                  class="cursor-pointer"
                  @click="showPassword = !showPassword"
                />
              </template>
            </q-input>
            <q-input
              v-model="confirmation"
              :type="showPassword ? 'text' : 'password'"
              data-testid="reset-confirmation"
              outlined
              stack-label
              label="Confirmer le mot de passe"
              autocomplete="new-password"
              class="q-mb-md"
              :rules="[(v) => v === password || 'Les mots de passe ne correspondent pas']"
            />
            <q-btn
              type="submit"
              data-testid="reset-submit"
              color="primary"
              :label="invitation ? 'Activer mon compte' : 'Valider'"
              class="full-width"
              :loading="submitting"
            />
          </q-form>
        </template>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import AppNotice from 'src/components/AppNotice.vue';
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { resetPassword } from 'src/api/passwordReset';

const route = useRoute();
// Le jeton arrive dans le lien de l'email.
const token = computed(() => String(route.query.token ?? ''));
// Même page, même endpoint pour un compte créé par un admin (A15) : seul le
// vocabulaire change, la personne n'a jamais eu de mot de passe à « réinitialiser ».
const invitation = computed(() => route.query.mode === 'invitation');

const password = ref('');
const confirmation = ref('');
const showPassword = ref(false);
const submitting = ref(false);
const doneMessage = ref<string | null>(null);
const errorMessage = ref<string | null>(null);

async function onSubmit() {
  if (password.value !== confirmation.value) return;
  submitting.value = true;
  errorMessage.value = null;
  try {
    doneMessage.value = await resetPassword(token.value, password.value);
  } catch (err) {
    errorMessage.value =
      extractError(err) ?? 'Lien invalide ou expiré. Demandez un nouveau lien de réinitialisation.';
  } finally {
    submitting.value = false;
  }
}

function extractError(err: unknown): string | null {
  const data = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data;
  return data?.error?.message ?? null;
}
</script>
