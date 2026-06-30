<template>
  <q-page class="payment-return-page flex flex-center">
    <div class="text-center q-pa-xl" style="max-width: 480px">
      <!-- Polling in progress -->
      <template v-if="state === 'polling'">
        <q-spinner color="primary" size="3em" class="q-mb-md" />
        <div class="text-h6 q-mb-sm">Vérification du paiement…</div>
        <div class="text-body2 text-grey-7">
          Merci de patienter, nous vérifions votre transaction.
        </div>
      </template>

      <!-- Success -->
      <template v-else-if="state === 'success'">
        <q-icon name="check_circle" color="positive" size="4em" class="q-mb-md" />
        <div class="text-h6 q-mb-sm">Paiement accepté !</div>
        <div class="text-body2 text-grey-7 q-mb-lg">
          Votre commande a bien été enregistrée. Vous recevrez une confirmation par email.
        </div>
        <q-btn color="primary" label="Retour au catalogue" :to="{ name: 'catalogue' }" />
      </template>

      <!-- Failure -->
      <template v-else-if="state === 'failure'">
        <q-icon name="cancel" color="negative" size="4em" class="q-mb-md" />
        <div class="text-h6 q-mb-sm">Paiement refusé</div>
        <div class="text-body2 text-grey-7 q-mb-lg">
          Votre paiement n'a pas pu être traité. Vous pouvez réessayer ou contacter notre équipe.
        </div>
        <div class="row q-gutter-sm justify-center">
          <q-btn outline color="primary" label="Réessayer" :to="{ name: 'checkout' }" />
          <q-btn flat color="grey-7" label="Retour au panier" :to="{ name: 'cart' }" />
        </div>
      </template>

      <!-- Error (no payment id, network error, timeout) -->
      <template v-else-if="state === 'error'">
        <q-icon name="warning" color="warning" size="4em" class="q-mb-md" />
        <div class="text-h6 q-mb-sm">Vérification impossible</div>
        <div class="text-body2 text-grey-7 q-mb-lg">
          {{ errorMessage }}
        </div>
        <div class="row q-gutter-sm justify-center">
          <q-btn color="primary" label="Retour au panier" :to="{ name: 'cart' }" />
        </div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { getMyPaymentStatus } from 'src/api/payments';

const PENDING_PAYMENT_KEY = 'payzen.pending_payment_id';
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 120_000; // 2 minutes max

type PageState = 'polling' | 'success' | 'failure' | 'error';

const state = ref<PageState>('polling');
const errorMessage = ref('');

let intervalId: ReturnType<typeof setInterval> | null = null;
let timeoutId: ReturnType<typeof setTimeout> | null = null;

onMounted(() => {
  const paymentId = localStorage.getItem(PENDING_PAYMENT_KEY);

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

    if (!status.is_terminal) return;

    stopPolling();
    localStorage.removeItem(PENDING_PAYMENT_KEY);

    if (status.status_name === 'Completed') {
      state.value = 'success';
    } else {
      state.value = 'failure';
    }
  } catch {
    // Network errors are transient — keep polling unless timeout fires
  }
}
</script>
