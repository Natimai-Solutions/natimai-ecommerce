<template>
  <q-page class="balance page-container app-page">
    <router-link :to="{ name: 'order-tracking', params: { id: orderId } }" class="balance__back">
      <q-icon name="ph:arrow-left" size="16px" /> {{ $t('balance.order', { ref: orderLabel }) }}
    </router-link>
    <h1 class="page-title balance__title">
      {{ payingBalance ? $t('balance.title') : $t('balance.title_order') }}
    </h1>

    <div v-if="loading" aria-busy="true">
      <q-skeleton type="text" width="40%" /><q-skeleton type="text" width="60%" />
    </div>

    <AppNotice v-else-if="errorMessage && !order" tone="error">{{ errorMessage }}</AppNotice>

    <template v-else-if="order">
      <AppNotice
        v-if="nothingDue"
        :tone="fullyPaid ? 'success' : 'info'"
        data-testid="balance-settled"
      >
        {{ fullyPaid ? $t('balance.settled') : $t('balance.not_payable') }}
        <template #action>
          <q-btn
            flat
            :label="$t('balance.see_order')"
            :to="{ name: 'order-tracking', params: { id: order.id } }"
          />
        </template>
      </AppNotice>

      <div v-else class="balance__layout">
        <section class="balance__main">
          <AppNotice v-if="errorMessage" tone="error" class="q-mb-md">{{ errorMessage }}</AppNotice>
          <AppNotice
            v-else-if="route.query.start_failed && !formToken && !instructions"
            tone="warning"
            class="q-mb-md"
            data-testid="payment-start-failed"
          >
            {{ $t('balance.start_failed') }}
          </AppNotice>

          <template v-if="instructions">
            <AppNotice tone="success" class="q-mb-md">
              {{ $t('balance.request_saved') }}
            </AppNotice>
            <p class="balance__instructions">{{ instructions }}</p>
            <q-btn
              outline
              color="primary"
              :label="$t('balance.back_to_order')"
              :to="{ name: 'order-tracking', params: { id: order.id } }"
            />
          </template>

          <template v-else-if="!formToken">
            <div class="app-section__head">
              <h2 class="app-section__title">{{ $t('balance.method') }}</h2>
            </div>
            <AppNotice v-if="methods.length === 0" tone="warning">
              {{ $t('balance.no_methods') }}
            </AppNotice>
            <ChoiceList
              v-else
              v-model="selectedMethodId"
              :label="$t('balance.method_label')"
              :options="methodChoices"
            />
            <q-btn
              data-testid="balance-submit"
              unelevated
              color="primary"
              :label="$t('balance.pay', { amount: money(dueAmount) })"
              class="balance__submit"
              :loading="initiating"
              :disable="!selectedMethodId || initiating"
              @click="pay"
            />
          </template>

          <div v-show="formToken" class="balance__card-form">
            <div id="kr-smart-form-container" />
          </div>
        </section>

        <aside class="app-panel balance__summary" :aria-label="$t('balance.summary')">
          <h2 class="balance__summary-title">{{ $t('balance.summary_title') }}</h2>
          <div class="app-kv">
            <span>{{ $t('balance.total') }}</span>
            <span class="font-mono" data-testid="balance-total">{{ money(totalAmount) }}</span>
          </div>
          <p v-if="feeDelta !== 0" class="text-caption q-my-xs" data-testid="balance-fee-changed">
            {{ $t('balance.fee_changed') }}
          </p>
          <div v-if="payingBalance" class="app-kv">
            <span>{{ $t('balance.deposit_paid') }}</span>
            <span class="font-mono">{{ money(order.deposit_amount) }}</span>
          </div>
          <div class="app-kv app-kv--total">
            <span>
              {{
                payingBalance
                  ? $t('balance.balance_due')
                  : order.pay_now_kind === 'deposit'
                    ? $t('balance.deposit_due')
                    : $t('balance.amount_due')
              }}
            </span>
            <span class="font-mono" data-testid="balance-amount">{{ money(dueAmount) }}</span>
          </div>
        </aside>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { usePageMeta } from '@/composables/usePageMeta';
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { orderRef } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import ChoiceList, { type ChoiceOption } from '@/components/ChoiceList.vue';
import { useAuthStore } from '@/stores/auth';
import { useCurrencyStore } from '@/stores/currency';
import { getMyOrder, type OrderDetail } from '@/api/orders';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';
import {
  initiatePayment,
  listMyPaymentMethods,
  paymentReturnQuery,
  type PaymentMethod,
} from '@/api/payments';
import { PENDING_PAYMENT_KEY, loadPayzenSmartForm } from '@/utils/payzen';

const { t, locale } = useI18n();

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();

const orderId = computed(() => String(route.params.id ?? ''));
const loading = ref(true);
const errorMessage = ref<string | null>(null);
const order = ref<OrderDetail | null>(null);
const methods = ref<PaymentMethod[]>([]);
const selectedMethodId = ref<string | null>(null);
const initiating = ref(false);
const formToken = ref<string | null>(null);
const instructions = ref<string | null>(null);

const orderLabel = computed(() =>
  order.value ? orderRef(order.value.order_number, order.value.id) : orderId.value.slice(0, 8),
);
/*
 * The part payable now. This page only paid the balance of a deposit order:
 * an order whose first payment failed or was abandoned (card refused, PayPal
 * left, page reloaded during the card form) had no way to be paid at all —
 * the cart was already emptied (functional audit, November 2026).
 */
const baseDueAmount = computed(() => order.value?.pay_now_amount ?? '0');
const billedFee = computed(() => Number.parseFloat(order.value?.payment_fee_amount ?? '0') || 0);
function feeOf(method: PaymentMethod): number {
  return Number.parseFloat(method.fee ?? '0') || 0;
}
/**
 * An order still entirely unpaid can change its payment method: the API
 * re-bills it that method's fee, so the amount follows the method picked.
 * A deposit or a balance keeps the amount of the order.
 */
const rebillable = computed(() => order.value?.pay_now_kind === 'full');
const selectedMethod = computed(
  () => methods.value.find((m) => m.id === selectedMethodId.value) ?? null,
);
const feeDelta = computed(() =>
  rebillable.value &&
  selectedMethod.value &&
  // The method the order is billed for keeps the fee it was quoted.
  selectedMethod.value.id !== order.value?.payment_method_id
    ? feeOf(selectedMethod.value) - billedFee.value
    : 0,
);
const dueAmount = computed(() => {
  if (feeDelta.value === 0) return baseDueAmount.value;
  const decimals = (baseDueAmount.value.split('.')[1] ?? '').length;
  return (Number.parseFloat(baseDueAmount.value) + feeDelta.value).toFixed(decimals);
});
const totalAmount = computed(() => {
  const total = order.value?.total_amount ?? '0';
  if (feeDelta.value === 0) return total;
  const decimals = (total.split('.')[1] ?? '').length;
  return (Number.parseFloat(total) + feeDelta.value).toFixed(decimals);
});
/** The API refuses these for a deposit (other fee) or a balance (dearer). */
function methodRefused(method: PaymentMethod): boolean {
  if (rebillable.value || method.id === order.value?.payment_method_id) return false;
  const fee = feeOf(method);
  return payingBalance.value ? fee > billedFee.value : fee !== billedFee.value;
}
const payingBalance = computed(() => order.value?.pay_now_kind === 'balance');
const nothingDue = computed(
  () => !order.value?.pay_now_kind || !(Number.parseFloat(baseDueAmount.value) > 0),
);

/** Nothing to pay online is not « paid »: a cancelled order, one under review
 * or one settled at the counter by instalments said « intégralement réglée ». */
const fullyPaid = computed(() => !(Number.parseFloat(order.value?.amount_due ?? '0') > 0));

function money(raw: string): string {
  return orderMoney(raw, order.value?.currency, currencyStore.reference);
}

const methodChoices = computed<ChoiceOption[]>(() =>
  methods.value.map((m) => ({
    value: m.id,
    title: m.name,
    caption:
      rebillable.value && feeOf(m) > 0
        ? [m.description, t('balance.method_fee', { amount: money(String(feeOf(m))) })]
            .filter(Boolean)
            .join(' — ')
        : m.description,
    testid: `balance-method-${m.provider_code}`,
  })),
);

async function pay() {
  if (!order.value || !selectedMethodId.value) return;
  initiating.value = true;
  errorMessage.value = null;
  try {
    const returnUrl = `${window.location.origin}/paiement/retour`;
    const result = await initiatePayment({
      payment_method_id: selectedMethodId.value,
      amount: dueAmount.value,
      currency: order.value.currency ?? currencyStore.reference,
      order_id: order.value.id,
      return_url: returnUrl,
    });
    if (result.form_token && result.server_url && result.public_key) {
      localStorage.setItem(PENDING_PAYMENT_KEY, result.payment_id);
      formToken.value = result.form_token;
      await loadPayzenSmartForm({
        serverUrl: result.server_url,
        publicKey: result.public_key,
        token: result.form_token,
        returnUrl: `${returnUrl}?${paymentReturnQuery(
          result.payment_id,
          result.payment_status_token,
        )}`,
        language: locale.value,
      });
      return;
    }
    if (result.redirect_url) {
      localStorage.setItem(PENDING_PAYMENT_KEY, result.payment_id);
      window.location.assign(result.redirect_url);
      return;
    }
    if (result.instructions) {
      instructions.value = result.instructions;
      return;
    }
    errorMessage.value = t('balance.method_unavailable');
  } catch (err) {
    errorMessage.value =
      apiErrorMessage(err) ??
      (payingBalance.value ? t('balance.failed') : t('balance.failed_order'));
  } finally {
    initiating.value = false;
  }
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    await router.replace({
      name: 'login',
      query: { redirect: `/mon-compte/commandes/${orderId.value}/solde` },
    });
    return;
  }
  try {
    order.value = await getMyOrder(orderId.value);
    if (!nothingDue.value) {
      const eligible = await listMyPaymentMethods(Number.parseFloat(baseDueAmount.value));
      methods.value = eligible.filter((m) => !methodRefused(m));
      // The order's own method first: its fee is the one the order carries.
      const chosen = methods.value.find((m) => m.id === order.value?.payment_method_id);
      selectedMethodId.value = chosen?.id ?? methods.value[0]?.id ?? null;
    }
  } catch (err) {
    errorMessage.value =
      apiErrorMessage(err, { notFound: t('balance.not_found') }) ?? t('balance.load_failed');
  } finally {
    loading.value = false;
  }
});

usePageMeta(() => ({
  title: payingBalance.value ? t('balance.title') : t('balance.title_order'),
  noindex: true,
}));
</script>

<style scoped lang="scss">
.balance__back {
  margin-bottom: 20px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.balance__title {
  margin-bottom: 32px;
}

.balance__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 64px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
  }
}

.balance__summary {
  position: sticky;
  top: 88px;

  @media (max-width: 1023px) {
    position: static;
    order: -1;
  }
}

.balance__summary-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.balance__submit {
  width: 100%;
  min-height: 48px;
  margin-top: 24px;
}

.balance__instructions {
  margin: 0 0 20px;
  white-space: pre-line;
  line-height: 1.6;
}

.balance__card-form {
  max-width: 480px;
}
</style>
