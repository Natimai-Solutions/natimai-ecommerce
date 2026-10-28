<template>
  <q-page class="page-container">
    <div class="app-result" aria-live="polite">
      <template v-if="state === 'polling'">
        <q-spinner size="44px" class="app-result__icon" />
        <h1>{{ $t('payment_return.checking') }}</h1>
        <p>
          {{ viaPaypal ? $t('payment_return.wait_paypal') : $t('payment_return.wait_bank') }}
        </p>
      </template>

      <template v-else-if="state === 'success'">
        <q-icon name="ph:check-circle" size="52px" class="app-result__icon app-result__icon--ok" />
        <h1>
          {{ authorizedOnly ? $t('payment_return.authorized') : $t('payment_return.accepted') }}
        </h1>
        <p>
          <template v-if="authorizedOnly">
            {{ $t('payment_return.authorized_text') }}
          </template>
          <template v-else>{{ $t('payment_return.order_saved') }}</template>
          {{ $t('payment_return.confirmation_sent') }}
        </p>
        <GuestAccountOffer class="q-mb-md" />
        <div class="app-result__actions">
          <q-btn
            v-if="orderId"
            unelevated
            color="primary"
            :label="$t('payment_return.see_my_order')"
            :to="{ name: 'order-tracking', params: { id: orderId } }"
          />
          <q-btn
            outline
            color="primary"
            :label="$t('payment_return.continue')"
            :to="{ name: 'catalogue' }"
          />
        </div>
      </template>

      <template v-else-if="state === 'failure'">
        <q-icon name="ph:x-circle" size="52px" class="app-result__icon app-result__icon--danger" />
        <h1>{{ $t('payment_return.refused') }}</h1>
        <p>
          {{ $t('payment_return.refused_text') }}
        </p>
        <div class="app-result__actions">
          <q-btn
            v-if="orderId"
            unelevated
            color="primary"
            :label="$t('payment_return.see_order')"
            :to="{ name: 'order-tracking', params: { id: orderId } }"
          />
          <q-btn
            outline
            color="primary"
            :label="$t('payment_return.back_to_cart')"
            :to="{ name: 'cart' }"
          />
        </div>
      </template>

      <template v-else-if="state === 'cancelled'">
        <q-icon name="ph:arrow-u-up-left" size="52px" class="app-result__icon" />
        <h1>{{ $t('payment_return.cancelled') }}</h1>
        <p data-testid="payment-cancelled">
          {{ $t('payment_return.cancelled_text') }}
        </p>
        <div class="app-result__actions">
          <q-btn
            v-if="orderId"
            unelevated
            color="primary"
            :label="$t('payment_return.see_order')"
            :to="{ name: 'order-tracking', params: { id: orderId } }"
          />
          <q-btn
            outline
            color="primary"
            :label="$t('payment_return.my_orders')"
            :to="{ name: 'account', query: { tab: 'orders' } }"
          />
        </div>
      </template>

      <template v-else>
        <q-icon name="ph:warning" size="52px" class="app-result__icon app-result__icon--warn" />
        <h1>{{ $t('payment_return.check_failed') }}</h1>
        <p>{{ errorMessage }}</p>
        <div class="app-result__actions">
          <q-btn
            unelevated
            color="primary"
            :label="$t('payment_return.my_orders')"
            :to="{ name: 'account', query: { tab: 'orders' } }"
          />
          <q-btn
            outline
            color="primary"
            :label="$t('payment_return.back_to_cart')"
            :to="{ name: 'cart' }"
          />
        </div>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { usePageMeta } from '@/composables/usePageMeta';
import { useI18n } from 'vue-i18n';
import { onMounted, onUnmounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { confirmMyPayment, getMyPaymentStatus, type PaymentStatusResponse } from '@/api/payments';
import { PENDING_PAYMENT_KEY } from '@/utils/payzen';
import GuestAccountOffer from '@/components/GuestAccountOffer.vue';

const { t } = useI18n();
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 120_000; // 2 minutes max

type PageState = 'polling' | 'success' | 'failure' | 'cancelled' | 'error';

const state = ref<PageState>('polling');
const errorMessage = ref('');
const orderId = ref<string | null>(null);
// Capture différée : la carte est autorisée, le débit suit à l'expédition.
const authorizedOnly = ref(false);

let intervalId: ReturnType<typeof setInterval> | null = null;
let timeoutId: ReturnType<typeof setTimeout> | null = null;

const route = useRoute();

function queryParam(name: string): string | null {
  const raw = route.query[name];
  const value = Array.isArray(raw) ? raw[0] : raw;
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

// PayPal renvoie ici après approbation (?provider=paypal) ou abandon
// (&cancelled=1) : la boutique finalise elle-même le paiement.
const viaPaypal = queryParam('provider') === 'paypal';

/**
 * The payment being polled.
 *
 * The query string comes first: 3-D Secure often completes in the bank's own
 * app or another browser, so the tab that lands here may never have written
 * the local key. Falling back to localStorage keeps older links working.
 */
function resolvePaymentId(): string | null {
  return queryParam('payment') ?? localStorage.getItem(PENDING_PAYMENT_KEY);
}

onMounted(() => {
  const paymentId = resolvePaymentId();

  if (!paymentId) {
    state.value = 'error';
    errorMessage.value = t('payment_return.none_pending');
    return;
  }

  if (viaPaypal && queryParam('cancelled')) {
    localStorage.removeItem(PENDING_PAYMENT_KEY);
    state.value = 'cancelled';
    void getMyPaymentStatus(paymentId)
      .then((status) => (orderId.value = status.order_id ?? null))
      .catch(() => undefined);
    return;
  }

  if (viaPaypal) {
    void confirmThenPoll(paymentId);
    return;
  }

  startPolling(paymentId);
});

/**
 * PayPal : la capture se fait côté serveur au retour du client. Si elle
 * échoue (réseau, PayPal lent), on attend la notification de PayPal.
 */
async function confirmThenPoll(paymentId: string) {
  try {
    const status = await confirmMyPayment(paymentId);
    if (applyStatus(status)) return;
  } catch {
    // The provider's notification may still settle it — keep polling.
  }
  startPolling(paymentId);
}

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
      errorMessage.value = t('payment_return.too_long');
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
    if (applyStatus(status)) stopPolling();
  } catch {
    // Network errors are transient — keep polling unless timeout fires
  }
}

/** Show a decided payment; false while it is still in progress. */
function applyStatus(status: PaymentStatusResponse): boolean {
  orderId.value = status.order_id ?? null;
  if (!status.is_terminal) return false;

  localStorage.removeItem(PENDING_PAYMENT_KEY);
  if (status.status_name === 'Completed' || status.status_name === 'Authorized') {
    authorizedOnly.value = status.status_name === 'Authorized';
    state.value = 'success';
  } else {
    state.value = 'failure';
  }
  return true;
}

usePageMeta(() => ({ title: t('payment_return.checking'), noindex: true }));
</script>
