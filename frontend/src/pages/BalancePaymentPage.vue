<template>
  <q-page class="balance page-container app-page">
    <router-link :to="{ name: 'order-tracking', params: { id: orderId } }" class="balance__back">
      <q-icon name="ph:arrow-left" size="16px" /> Commande {{ orderLabel }}
    </router-link>
    <h1 class="page-title balance__title">Régler le solde</h1>

    <div v-if="loading" aria-busy="true">
      <q-skeleton type="text" width="40%" /><q-skeleton type="text" width="60%" />
    </div>

    <AppNotice v-else-if="errorMessage && !order" tone="error">{{ errorMessage }}</AppNotice>

    <template v-else-if="order">
      <AppNotice v-if="nothingDue" tone="success" data-testid="balance-settled">
        Cette commande est intégralement réglée.
        <template #action>
          <q-btn
            flat
            label="Voir la commande"
            :to="{ name: 'order-tracking', params: { id: order.id } }"
          />
        </template>
      </AppNotice>

      <div v-else class="balance__layout">
        <section class="balance__main">
          <AppNotice v-if="errorMessage" tone="error" class="q-mb-md">{{ errorMessage }}</AppNotice>

          <template v-if="instructions">
            <AppNotice tone="success" class="q-mb-md">
              Votre demande de règlement a bien été enregistrée.
            </AppNotice>
            <p class="balance__instructions">{{ instructions }}</p>
            <q-btn
              outline
              color="primary"
              label="Retour à la commande"
              :to="{ name: 'order-tracking', params: { id: order.id } }"
            />
          </template>

          <template v-else-if="!formToken">
            <div class="app-section__head">
              <h2 class="app-section__title">Moyen de paiement</h2>
            </div>
            <AppNotice v-if="methods.length === 0" tone="warning">
              Aucun moyen de paiement n'est disponible pour votre compte. Contactez notre équipe.
            </AppNotice>
            <ChoiceList
              v-else
              v-model="selectedMethodId"
              label="Moyen de paiement"
              :options="methodChoices"
            />
            <q-btn
              data-testid="balance-submit"
              unelevated
              color="primary"
              :label="`Régler ${money(order.balance_amount)}`"
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

        <aside class="app-panel balance__summary" aria-label="Récapitulatif">
          <h2 class="balance__summary-title">Récapitulatif</h2>
          <div class="app-kv">
            <span>Total de la commande</span>
            <span class="font-mono">{{ money(order.total_amount) }}</span>
          </div>
          <div class="app-kv">
            <span>Acompte déjà versé</span>
            <span class="font-mono">{{ money(order.deposit_amount) }}</span>
          </div>
          <div class="app-kv app-kv--total">
            <span>Solde à régler</span>
            <span class="font-mono" data-testid="balance-amount">{{
              money(order.balance_amount)
            }}</span>
          </div>
        </aside>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { orderRef } from '@app/utils';

import AppNotice from '@/components/AppNotice.vue';
import ChoiceList, { type ChoiceOption } from '@/components/ChoiceList.vue';
import { useAuthStore } from '@/stores/auth';
import { useCurrencyStore } from '@/stores/currency';
import { getMyOrder, type Order } from '@/api/orders';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';
import { initiatePayment, listMyPaymentMethods, type PaymentMethod } from '@/api/payments';
import { PENDING_PAYMENT_KEY, loadPayzenSmartForm } from '@/utils/payzen';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();

const orderId = computed(() => String(route.params.id ?? ''));
const loading = ref(true);
const errorMessage = ref<string | null>(null);
const order = ref<Order | null>(null);
const methods = ref<PaymentMethod[]>([]);
const selectedMethodId = ref<string | null>(null);
const initiating = ref(false);
const formToken = ref<string | null>(null);
const instructions = ref<string | null>(null);

const orderLabel = computed(() =>
  order.value ? orderRef(order.value.order_number, order.value.id) : orderId.value.slice(0, 8),
);
const nothingDue = computed(
  () =>
    !order.value ||
    order.value.payment_plan !== 'deposit' ||
    order.value.balance_paid_at !== null ||
    Number.parseFloat(order.value.balance_amount) <= 0,
);

function money(raw: string): string {
  return orderMoney(raw, order.value?.currency, currencyStore.reference);
}

const methodChoices = computed<ChoiceOption[]>(() =>
  methods.value.map((m) => ({
    value: m.id,
    title: m.name,
    caption: m.description,
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
      amount: order.value.balance_amount,
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
        returnUrl: `${returnUrl}?payment=${encodeURIComponent(result.payment_id)}`,
      });
      return;
    }
    if (result.instructions) {
      instructions.value = result.instructions;
      return;
    }
    errorMessage.value = "Le moyen de paiement sélectionné n'est pas disponible pour le moment.";
  } catch (err) {
    errorMessage.value =
      apiErrorMessage(err) ?? 'Le règlement du solde a échoué. Veuillez réessayer.';
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
      methods.value = await listMyPaymentMethods(Number.parseFloat(order.value.balance_amount));
      selectedMethodId.value = methods.value[0]?.id ?? null;
    }
  } catch (err) {
    errorMessage.value =
      apiErrorMessage(err, { notFound: 'Cette commande est introuvable.' }) ??
      'Impossible de charger cette commande.';
  } finally {
    loading.value = false;
  }
});
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
