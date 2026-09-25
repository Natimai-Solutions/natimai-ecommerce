<template>
  <q-page class="balance-payment-page q-pa-md">
    <div class="row items-center q-mb-md">
      <q-btn flat dense round icon="arrow_back" class="q-mr-sm" :to="{ name: 'order-tracking', params: { id: orderId } }" />
      <div class="text-h6 col">Régler le solde de la commande {{ orderLabel }}</div>
    </div>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner color="primary" size="2.5em" />
    </div>

    <q-banner v-else-if="errorMessage" class="bg-red-1 text-red-9" rounded>
      <template #avatar><q-icon name="error_outline" /></template>
      {{ errorMessage }}
    </q-banner>

    <template v-else-if="order">
      <q-banner v-if="nothingDue" class="bg-green-1 text-green-9" rounded data-testid="balance-settled">
        <template #avatar><q-icon name="check_circle" /></template>
        Cette commande est intégralement réglée.
      </q-banner>

      <div v-else class="row q-col-gutter-md">
        <div class="col-12 col-md-5">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 text-weight-medium q-mb-sm">Récapitulatif</div>
              <div class="row justify-between q-mb-xs">
                <span>Total de la commande</span><span>{{ money(order.total_amount) }}</span>
              </div>
              <div class="row justify-between q-mb-xs">
                <span>Acompte déjà versé</span><span>{{ money(order.deposit_amount) }}</span>
              </div>
              <q-separator class="q-my-sm" />
              <div class="row justify-between text-weight-bold">
                <span>Solde à régler</span>
                <span data-testid="balance-amount">{{ money(order.balance_amount) }}</span>
              </div>
            </q-card-section>
          </q-card>
        </div>

        <div class="col-12 col-md-7">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 text-weight-medium q-mb-md">Paiement du solde</div>

              <template v-if="instructions">
                <q-banner class="bg-green-1 text-green-9 q-mb-md" rounded>
                  <template #avatar><q-icon name="check_circle" /></template>
                  Votre demande de règlement a bien été enregistrée.
                </q-banner>
                <div class="text-body2" style="white-space: pre-line">{{ instructions }}</div>
              </template>

              <template v-else-if="!formToken">
                <q-banner v-if="methods.length === 0" class="bg-orange-1 text-orange-10" rounded>
                  Aucun moyen de paiement n'est disponible pour votre compte. Veuillez contacter notre équipe.
                </q-banner>
                <q-list v-else bordered separator class="rounded-borders q-mb-md">
                  <q-item
                    v-for="m in methods"
                    :key="m.id"
                    v-ripple
                    clickable
                    :active="selectedMethodId === m.id"
                    active-class="bg-blue-1"
                    @click="selectedMethodId = m.id"
                  >
                    <q-item-section avatar>
                      <q-radio v-model="selectedMethodId" :val="m.id" />
                    </q-item-section>
                    <q-item-section>
                      <q-item-label>{{ m.name }}</q-item-label>
                      <q-item-label v-if="m.description" caption>{{ m.description }}</q-item-label>
                    </q-item-section>
                  </q-item>
                </q-list>
                <q-btn
                  data-testid="balance-submit"
                  color="primary"
                  icon="payments"
                  :label="`Régler ${money(order.balance_amount)}`"
                  size="lg"
                  class="full-width"
                  :loading="initiating"
                  :disable="!selectedMethodId || initiating"
                  @click="pay"
                />
              </template>

              <div v-show="formToken">
                <div id="kr-smart-form-container" />
              </div>
            </q-card-section>
          </q-card>
        </div>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { formatXpf, orderRef } from '@app/utils';
import { useAuthStore } from 'src/stores/auth';
import { getMyOrder, type Order } from 'src/api/orders';
import { initiatePayment, listMyPaymentMethods, type PaymentMethod } from 'src/api/payments';
import { PENDING_PAYMENT_KEY, loadPayzenSmartForm } from 'src/utils/payzen';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

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
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? formatXpf(n) : raw;
}

function extractError(err: unknown): string | null {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
    }
  }
  return null;
}

async function pay() {
  if (!order.value || !selectedMethodId.value) return;
  initiating.value = true;
  errorMessage.value = null;
  try {
    const returnUrl = `${window.location.origin}/paiement/retour`;
    const result = await initiatePayment({
      payment_method_id: selectedMethodId.value,
      amount: order.value.balance_amount,
      currency: order.value.currency ?? 'XPF',
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
    errorMessage.value = extractError(err) ?? 'Le règlement du solde a échoué. Veuillez réessayer.';
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
    if (!order.value) {
      errorMessage.value = 'Cette commande est introuvable.';
      return;
    }
    if (!nothingDue.value) {
      methods.value = await listMyPaymentMethods(Number.parseFloat(order.value.balance_amount));
      selectedMethodId.value = methods.value[0]?.id ?? null;
    }
  } catch (err) {
    errorMessage.value = extractError(err) ?? 'Impossible de charger cette commande.';
  } finally {
    loading.value = false;
  }
});
</script>
