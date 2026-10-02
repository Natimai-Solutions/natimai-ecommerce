<template>
  <q-page class="auth-page flex flex-center">
    <q-card flat class="auth-card">
      <q-card-section>
        <h1 class="auth-title">
          {{ invitation ? $t('auth.activate_title') : $t('auth.new_password_title') }}
        </h1>
        <div v-if="invitation" class="auth-lead q-mt-xs">
          {{ $t('auth.invitation_lead') }}
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <AppNotice v-if="!token" tone="error">
          {{ $t('auth.link_incomplete') }}
        </AppNotice>

        <template v-else-if="doneMessage">
          <AppNotice tone="success" class="q-mb-md">
            {{ doneMessage }}
          </AppNotice>
          <q-btn
            color="primary"
            :label="$t('auth.sign_in')"
            class="full-width"
            :to="{ name: 'login' }"
          />
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
              :label="$t('auth.new_password')"
              autocomplete="new-password"
              class="q-mb-sm"
              :rules="[
                (v) => !!v || $t('auth.password_required'),
                (v) => v.length >= 8 || $t('auth.min_8b'),
              ]"
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
              v-model="confirmation"
              :type="showPassword ? 'text' : 'password'"
              data-testid="reset-confirmation"
              outlined
              stack-label
              :label="$t('auth.password_confirm')"
              autocomplete="new-password"
              class="q-mb-md"
              :rules="[(v) => v === password || $t('auth.password_mismatch')]"
            />
            <q-btn
              type="submit"
              data-testid="reset-submit"
              color="primary"
              :label="invitation ? $t('auth.activate_my_account') : $t('auth.validate')"
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
import { usePageMeta } from '@/composables/usePageMeta';
import { useI18n } from 'vue-i18n';
import { apiErrorMessage } from '@/utils/errors';
import AppNotice from '@app/ui/AppNotice.vue';
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { resetPassword } from '@/api/passwordReset';

const { t } = useI18n();

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
    errorMessage.value = apiErrorMessage(err) ?? t('auth.link_invalid');
  } finally {
    submitting.value = false;
  }
}

usePageMeta(() => ({ title: t('auth.new_password_title'), noindex: true }));
</script>
