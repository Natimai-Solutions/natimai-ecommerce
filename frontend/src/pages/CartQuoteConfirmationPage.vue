<template>
  <q-page class="page-container">
    <div class="app-result">
      <q-icon
        name="ph:paper-plane-tilt"
        size="52px"
        class="app-result__icon app-result__icon--ok"
      />
      <h1>{{ $t('quote_sent.title') }}</h1>
      <p>
        {{ $t('quote_sent.text') }}
      </p>
      <p v-if="customerEmail">
        <i18n-t keypath="quote_sent.sent_to" tag="span"
          ><template #email
            ><span class="text-ink">{{ customerEmail }}</span></template
          ></i18n-t
        >
      </p>
      <div class="app-result__actions">
        <q-btn
          v-if="authStore.isAuthenticated"
          unelevated
          color="primary"
          :label="$t('quote_sent.my_quotes')"
          :to="{ name: 'account', query: { tab: 'quotes' } }"
        />
        <q-btn outline color="primary" :label="$t('quote_sent.back')" :to="{ name: 'catalogue' }" />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const authStore = useAuthStore();

const customerEmail = computed(() => {
  const value = route.query.email;
  if (typeof value !== 'string') return '';

  const normalized = value.trim().toLowerCase();
  return /^(?:[^\s@]+)@(?:[^\s@]+)\.[^\s@]+$/.test(normalized) ? normalized : '';
});
</script>
