<template>
  <div v-if="authStore.profile?.is_guest" class="app-panel guest-offer" data-testid="guest-offer">
    <q-icon name="ph:user-plus" size="24px" class="guest-offer__icon" />
    <div class="guest-offer__body">
      <p class="guest-offer__title">{{ $t('guest.offer_title') }}</p>
      <p class="guest-offer__text">
        {{ sent ?? $t('guest.offer_text', { email: authStore.profile.email }) }}
      </p>
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
    </div>
    <q-btn
      v-if="!sent"
      unelevated
      no-caps
      color="primary"
      :label="$t('guest.offer_btn')"
      :loading="sending"
      data-testid="guest-offer-send"
      @click="send"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';

import AppNotice from '@app/ui/AppNotice.vue';
import { sendGuestActivationLink } from '@/api/profile';
import { useAuthStore } from '@/stores/auth';
import { apiErrorMessage } from '@/utils/errors';

/**
 * « Créer mon compte » for a customer who ordered without one: e-mails the
 * link that sets the password. Shows nothing for any other account.
 */
const { t } = useI18n();
const authStore = useAuthStore();

const sending = ref(false);
const sent = ref<string | null>(null);
const error = ref<string | null>(null);

async function send() {
  sending.value = true;
  error.value = null;
  try {
    sent.value = await sendGuestActivationLink();
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('guest.offer_failed');
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped lang="scss">
.guest-offer {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: center;
  text-align: left;
}

.guest-offer__icon {
  color: var(--n-accent);
}

.guest-offer__body {
  display: grid;
  flex: 1 1 260px;
  gap: 4px;
}

.guest-offer__title {
  margin: 0;
  font-weight: 600;
}

.guest-offer__text {
  margin: 0;
  font-size: 14px;
  color: var(--n-ink-2);
}
</style>
