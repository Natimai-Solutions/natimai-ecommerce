<template>
  <q-page class="flex flex-center q-pa-md">
    <q-card flat bordered style="width: min(420px, 100%)">
      <q-card-section>
        <div class="text-h6">Nouveau mot de passe</div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <q-banner v-if="!token" class="bg-red-1 text-red-9" rounded>
          <template #avatar><q-icon name="error_outline" /></template>
          Ce lien est incomplet. Demandez-en un nouveau depuis la page « mot de passe
          oublié ».
        </q-banner>

        <template v-else-if="doneMessage">
          <q-banner class="bg-green-1 text-green-9 q-mb-md" rounded>
            <template #avatar><q-icon name="check_circle" /></template>
            {{ doneMessage }}
          </q-banner>
          <q-btn
            color="primary"
            label="Se connecter"
            class="full-width"
            :to="{ name: 'login' }"
          />
        </template>

        <template v-else>
          <q-banner v-if="errorMessage" class="bg-red-1 text-red-9 q-mb-md" rounded>
            <template #avatar><q-icon name="error_outline" /></template>
            {{ errorMessage }}
          </q-banner>

          <q-form @submit.prevent="onSubmit">
            <q-input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              data-testid="reset-password"
              outlined
              dense
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
              dense
              label="Confirmer le mot de passe"
              autocomplete="new-password"
              class="q-mb-md"
              :rules="[(v) => v === password || 'Les mots de passe ne correspondent pas']"
            />
            <q-btn
              type="submit"
              data-testid="reset-submit"
              color="primary"
              label="Valider"
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
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { resetPassword } from 'src/api/passwordReset';

const route = useRoute();
// Le jeton arrive dans le lien de l'email.
const token = computed(() => String(route.query.token ?? ''));

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
      extractError(err) ??
      'Lien invalide ou expiré. Demandez un nouveau lien de réinitialisation.';
  } finally {
    submitting.value = false;
  }
}

function extractError(err: unknown): string | null {
  const data = (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data;
  return data?.error?.message ?? null;
}
</script>
