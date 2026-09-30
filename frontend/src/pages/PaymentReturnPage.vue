<template>
  <q-page class="page-container">
    <div class="app-result" aria-live="polite">
      <template v-if="state === 'polling'">
        <q-spinner size="44px" class="app-result__icon" />
        <h1>Vérification du paiement</h1>
        <p>Merci de patienter, nous confirmons la transaction auprès de la banque.</p>
      </template>

      <template v-else-if="state === 'success'">
        <q-icon name="ph:check-circle" size="52px" class="app-result__icon app-result__icon--ok" />
        <h1>{{ authorizedOnly ? 'Paiement autorisé' : 'Paiement accepté' }}</h1>
        <p>
          <template v-if="authorizedOnly">
            Votre carte est acceptée ; le débit aura lieu à l'expédition de la commande.
          </template>
          <template v-else>Votre commande est enregistrée.</template>
          Une confirmation vous est envoyée par e-mail.
        </p>
        <div class="app-result__actions">
          <q-btn
            v-if="orderId"
            unelevated
            color="primary"
            label="Voir ma commande"
            :to="{ name: 'order-tracking', params: { id: orderId } }"
          />
          <q-btn outline color="primary" label="Continuer mes achats" :to="{ name: 'catalogue' }" />
        </div>
      </template>

      <template v-else-if="state === 'failure'">
        <q-icon name="ph:x-circle" size="52px" class="app-result__icon app-result__icon--danger" />
        <h1>Paiement refusé</h1>
        <p>
          La transaction n'a pas abouti et rien n'a été débité. Vous pouvez réessayer, choisir un
          autre moyen de paiement ou contacter notre équipe.
        </p>
        <div class="app-result__actions">
          <q-btn
            v-if="orderId"
            unelevated
            color="primary"
            label="Voir la commande"
            :to="{ name: 'order-tracking', params: { id: orderId } }"
          />
          <q-btn outline color="primary" label="Retour au panier" :to="{ name: 'cart' }" />
        </div>
      </template>

      <template v-else>
        <q-icon name="ph:warning" size="52px" class="app-result__icon app-result__icon--warn" />
        <h1>Vérification impossible</h1>
        <p>{{ errorMessage }}</p>
        <div class="app-result__actions">
          <q-btn
            unelevated
            color="primary"
            label="Mes commandes"
            :to="{ name: 'account', query: { tab: 'orders' } }"
          />
          <q-btn outline color="primary" label="Retour au panier" :to="{ name: 'cart' }" />
        </div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { getMyPaymentStatus } from '@/api/payments';
import { PENDING_PAYMENT_KEY } from '@/utils/payzen';
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 120_000; // 2 minutes max

type PageState = 'polling' | 'success' | 'failure' | 'error';

const state = ref<PageState>('polling');
const errorMessage = ref('');
const orderId = ref<string | null>(null);
// Capture différée : la carte est autorisée, le débit suit à l'expédition.
const authorizedOnly = ref(false);

let intervalId: ReturnType<typeof setInterval> | null = null;
let timeoutId: ReturnType<typeof setTimeout> | null = null;

const route = useRoute();

/**
 * The payment being polled.
 *
 * The query string comes first: 3-D Secure often completes in the bank's own
 * app or another browser, so the tab that lands here may never have written
 * the local key. Falling back to localStorage keeps older links working.
 */
function resolvePaymentId(): string | null {
  const fromQuery = route.query.payment;
  const queryValue = Array.isArray(fromQuery) ? fromQuery[0] : fromQuery;
  if (typeof queryValue === 'string' && queryValue.trim()) return queryValue.trim();
  return localStorage.getItem(PENDING_PAYMENT_KEY);
}

onMounted(() => {
  const paymentId = resolvePaymentId();

  if (!paymentId) {
    state.value = 'error';
    errorMessage.value =
      "Aucune transaction en attente trouvée. Si vous venez d'effectuer un paiement, veuillez contacter notre équipe.";
    return;
  }

  startPolling(paymentId);
});

onUnmounted(() => {
  stopPolling();
});

function startPolling(paymentId: string) {
  // Kick off first check immediately
  void checkStatus(paymentId);

  intervalId = setInterval(() => {
    void checkStatus(paymentId);
  }, POLL_INTERVAL_MS);

  timeoutId = setTimeout(() => {
    stopPolling();
    if (state.value === 'polling') {
      state.value = 'error';
      errorMessage.value =
        'La vérification du paiement a pris trop longtemps. Veuillez vérifier votre email de confirmation ou contacter notre équipe.';
    }
  }, POLL_TIMEOUT_MS);
}

function stopPolling() {
  if (intervalId !== null) {
    clearInterval(intervalId);
    intervalId = null;
  }
  if (timeoutId !== null) {
    clearTimeout(timeoutId);
    timeoutId = null;
  }
}

async function checkStatus(paymentId: string) {
  try {
    const status = await getMyPaymentStatus(paymentId);

    orderId.value = status.order_id ?? null;
    if (!status.is_terminal) return;

    stopPolling();
    localStorage.removeItem(PENDING_PAYMENT_KEY);

    if (status.status_name === 'Completed' || status.status_name === 'Authorized') {
      authorizedOnly.value = status.status_name === 'Authorized';
      state.value = 'success';
    } else {
      state.value = 'failure';
    }
  } catch {
    // Network errors are transient — keep polling unless timeout fires
  }
}
</script>
