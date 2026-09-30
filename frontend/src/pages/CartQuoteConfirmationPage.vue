<template>
  <q-page class="page-container">
    <div class="app-result">
      <q-icon
        name="ph:paper-plane-tilt"
        size="52px"
        class="app-result__icon app-result__icon--ok"
      />
      <h1>Demande de devis envoyée</h1>
      <p>
        Votre panier est transmis à notre équipe. Le devis vous parvient par e-mail et se retrouve
        dans votre espace client, prêt à être commandé à ses prix.
      </p>
      <p v-if="customerEmail">
        Envoi à <span class="text-ink">{{ customerEmail }}</span>
      </p>
      <div class="app-result__actions">
        <q-btn
          v-if="authStore.isAuthenticated"
          unelevated
          color="primary"
          label="Mes devis"
          :to="{ name: 'account', query: { tab: 'quotes' } }"
        />
        <q-btn outline color="primary" label="Retour au catalogue" :to="{ name: 'catalogue' }" />
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
