<template>
  <q-page class="checkout page-container app-page">
    <router-link v-if="!orderPlaced" :to="{ name: 'cart' }" class="checkout__back">
      <q-icon name="ph:arrow-left" size="16px" /> {{ $t('checkout.back_to_cart') }}
    </router-link>
    <h1 class="page-title checkout__title">
      {{ orderPlaced ? $t('checkout.title_done') : $t('checkout.title') }}
    </h1>

    <AppNotice v-if="cartEmpty && !orderPlaced" tone="warning">
      {{ $t('checkout.cart_empty') }}
      <template #action>
        <q-btn flat :label="$t('checkout.see_catalogue')" :to="{ name: 'catalogue' }" />
      </template>
    </AppNotice>

    <div v-else class="checkout__layout" :class="{ 'checkout__layout--done': orderPlaced }">
      <div class="checkout__main">
        <AppNotice v-if="errorMessage" tone="error" class="checkout__notice">
          {{ errorMessage }}
        </AppNotice>
        <AppNotice
          v-if="quoteRequestId && !orderPlaced"
          tone="info"
          icon="ph:receipt"
          class="checkout__notice"
          data-testid="checkout-from-quote"
        >
          {{ $t('checkout.from_quote') }}
        </AppNotice>

        <!-- Paiement lié au compte : connexion requise -->
        <div v-if="!isAuthenticated" class="app-empty">
          <q-icon name="ph:lock-simple" size="36px" class="text-subtle" />
          <h3>{{ $t('checkout.login_title') }}</h3>
          <p>{{ $t('checkout.login_text') }}</p>
          <q-btn
            unelevated
            color="primary"
            :label="$t('checkout.login_btn')"
            :to="{ name: 'login', query: { redirect: '/checkout' } }"
          />
        </div>

        <div v-else-if="loadingMethods && !methods.length" aria-busy="true">
          <q-skeleton v-for="n in 3" :key="n" height="60px" class="checkout__skeleton" />
        </div>

        <AppNotice v-else-if="methods.length === 0 && !orderPlaced" tone="warning">
          {{ $t('checkout.no_methods') }}
        </AppNotice>

        <!-- PayPal : le client part approuver le paiement chez PayPal -->
        <AppNotice v-else-if="redirecting" tone="info" data-testid="checkout-redirecting">
          {{ $t('checkout.redirecting') }}
        </AppNotice>

        <!-- Confirmation : paiement manuel, bon de commande ou avoir -->
        <section v-else-if="instructions" class="confirmation">
          <div class="app-panel confirmation__head">
            <q-icon name="ph:check-circle" size="28px" class="confirmation__icon" />
            <div>
              <p data-testid="checkout-order-ref" class="confirmation__ref">
                {{ $t('checkout.order_ref') }} <span class="font-mono">{{ placedOrderRef }}</span>
              </p>
              <p class="confirmation__text">
                {{ $t('checkout.request_saved') }}
              </p>
              <p v-if="placedDeparture" class="confirmation__text">
                {{ $t('checkout.attached_departure', { name: placedDeparture.name }) }}
                <template v-if="nextDelivery"> {{ nextDelivery }}. </template>
              </p>
            </div>
          </div>

          <div class="app-section confirmation__instructions">
            <div class="app-section__head">
              <h2 class="app-section__title">{{ $t('checkout.to_pay') }}</h2>
            </div>
            <p class="confirmation__body" data-testid="checkout-instructions">{{ instructions }}</p>
          </div>

          <div v-if="needsUpload && !uploadDone" class="app-section">
            <div class="app-section__head">
              <h2 class="app-section__title">{{ $t('checkout.po_title') }}</h2>
              <p class="app-section__hint">
                {{ $t('checkout.po_hint') }}
              </p>
            </div>
            <AppNotice v-if="uploadError" dense tone="error" class="q-mb-sm">
              {{ uploadError }}
            </AppNotice>
            <div class="app-form">
              <q-file
                v-model="selectedFile"
                outlined
                :label="$t('checkout.po_file')"
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/*"
                :max-file-size="20 * 1024 * 1024"
              >
                <template #prepend><q-icon name="ph:paperclip" /></template>
              </q-file>
              <div class="app-form__actions">
                <q-btn
                  unelevated
                  color="primary"
                  :label="$t('checkout.po_send')"
                  :loading="uploading"
                  :disable="uploading || !selectedFile"
                  @click="uploadDocument"
                />
              </div>
            </div>
          </div>
          <AppNotice v-else-if="uploadDone" tone="success" icon="ph:check-circle" class="q-mb-md">
            {{ $t('checkout.po_received') }}
          </AppNotice>

          <div v-if="!needsUpload || uploadDone" class="confirmation__actions">
            <q-btn
              unelevated
              color="primary"
              :label="$t('checkout.my_orders')"
              :to="{ name: 'account', query: { tab: 'orders' } }"
            />
            <q-btn
              outline
              color="primary"
              :label="$t('checkout.continue')"
              :to="{ name: 'catalogue' }"
            />
          </div>
        </section>

        <!-- Étapes : adresse, livraison, règlement, paiement -->
        <template v-else-if="!formToken">
          <section class="step">
            <h2 class="step__title">
              <span class="step__num font-mono">1</span>{{ $t('checkout.step_address') }}
            </h2>
            <div v-if="addresses.length === 0" class="app-empty step__empty">
              <p>{{ $t('checkout.no_address') }}</p>
              <q-btn
                outline
                color="primary"
                :label="$t('checkout.add_address')"
                :to="{ name: 'account', query: { tab: 'addresses' } }"
              />
            </div>
            <ChoiceList
              v-else
              v-model="selectedAddressId"
              :label="$t('checkout.step_address')"
              :options="addressChoices"
            />
            <router-link
              v-if="addresses.length"
              :to="{ name: 'account', query: { tab: 'addresses' } }"
              class="text-link step__link"
            >
              {{ $t('checkout.manage_addresses') }}
            </router-link>
          </section>

          <section v-if="deliveryOptions.length > 0" class="step">
            <h2 class="step__title">
              <span class="step__num font-mono">2</span>{{ $t('checkout.step_delivery') }}
            </h2>
            <ChoiceList
              v-model="selectedDeliveryType"
              :label="$t('checkout.delivery_mode')"
              :options="deliveryChoices"
            />
          </section>

          <section v-if="quote?.deposit_available" class="step">
            <h2 class="step__title">
              <span class="step__num font-mono">{{ stepNumber('plan') }}</span
              >{{ $t('checkout.step_plan') }}
            </h2>
            <AppNotice
              v-if="quote.deposit_required"
              tone="info"
              icon="ph:piggy-bank"
              data-testid="checkout-deposit-required"
            >
              {{ $t('checkout.deposit_required', { pct: Number(quote.deposit_pct) }) }}
            </AppNotice>
            <ChoiceList
              v-else
              v-model="paymentPlan"
              :label="$t('checkout.step_plan')"
              :options="planChoices"
            />
          </section>

          <section class="step">
            <h2 class="step__title">
              <span class="step__num font-mono">{{ stepNumber('payment') }}</span
              >{{ $t('checkout.step_payment') }}
            </h2>
            <div
              v-if="quote && hasFee(quote.store_credit_available)"
              class="app-panel credit-toggle"
              data-testid="checkout-store-credit"
            >
              <q-icon name="ph:wallet" size="20px" class="text-muted" />
              <span class="credit-toggle__text">
                {{
                  $t('checkout.credit_available', {
                    amount: formatMoney(quote.store_credit_available),
                  })
                }}
              </span>
              <q-toggle
                v-model="useStoreCredit"
                :label="$t('checkout.use_credit')"
                left-label
                dense
              />
            </div>
            <ChoiceList
              v-if="!creditCoversEverything"
              v-model="selectedMethodId"
              :label="$t('checkout.payment_method')"
              :options="methodChoices"
            />
            <AppNotice v-else tone="success" data-testid="checkout-credit-covers">
              {{ $t('checkout.credit_covers') }}
            </AppNotice>
          </section>

          <div class="checkout__confirm">
            <q-checkbox v-model="cgvAccepted" data-testid="checkout-cgv" dense>
              <span class="checkout__cgv">
                {{ $t('checkout.cgv_accept') }}
                <router-link :to="{ name: 'cgv' }" target="_blank" @click.stop>
                  {{ $t('checkout.cgv_link') }}
                </router-link>
              </span>
            </q-checkbox>
            <q-btn
              data-testid="checkout-submit"
              unelevated
              color="primary"
              :label="submitLabel"
              class="checkout__submit"
              :loading="initiating"
              :disable="
                initiating ||
                !cgvAccepted ||
                (!selectedMethodId && !creditCoversEverything) ||
                !selectedAddressId ||
                (deliveryOptions.length > 0 && !selectedDeliveryType) ||
                quoteLoading ||
                !quote
              "
              @click="startPayment"
            />
            <p v-if="paysByCard" class="checkout__secure">
              <q-icon name="ph:lock-simple" size="14px" /> {{ $t('checkout.secure') }}
            </p>
          </div>
        </template>

        <!-- Formulaire carte (PayZen SmartForm) -->
        <div v-show="formToken" class="checkout__card-form">
          <p v-if="placedOrderRef" class="confirmation__ref">
            {{ $t('checkout.order_ref') }} <span class="font-mono">{{ placedOrderRef }}</span>
          </p>
          <div id="kr-smart-form-container" />
        </div>
      </div>

      <aside v-if="!orderPlaced" class="checkout__aside" :aria-label="$t('checkout.summary')">
        <div class="app-panel summary">
          <h2 class="summary__title">{{ $t('checkout.summary') }}</h2>
          <ul class="summary__lines">
            <li v-for="{ item, product } in cartStore.detailedItems" :key="item.id">
              <span class="summary__line-name">
                <span class="font-mono summary__qty">{{ item.quantity }}×</span>
                {{ product?.name ?? $t('checkout.item') }}
              </span>
              <span class="font-mono">{{ formatMoney(item.line_total) }}</span>
            </li>
          </ul>

          <!-- Le devis vient du backend (même calcul que la commande) : le
               total affiché est le montant débité, frais compris. -->
          <template v-if="quote">
            <div class="app-kv">
              <span>{{ $t('checkout.items') }}</span>
              <span class="font-mono">{{ formatMoney(quote.subtotal_amount) }}</span>
            </div>
            <div v-if="selectedDeliveryType" class="app-kv">
              <span>{{ $t('checkout.shipping') }}</span>
              <span class="font-mono" data-testid="checkout-quote-shipping">{{
                shippingOnlyAmount(quote) > 0
                  ? formatMoney(String(shippingOnlyAmount(quote)))
                  : $t('checkout.shipping_free')
              }}</span>
            </div>
            <div v-if="hasFee(quote.customs_declaration_fee)" class="app-kv">
              <span
                >{{ $t('checkout.customs') }} <small>{{ $t('checkout.customs_once') }}</small></span
              >
              <span class="font-mono">{{ formatMoney(quote.customs_declaration_fee) }}</span>
            </div>
            <div v-if="hasFee(quote.payment_fee_amount)" class="app-kv">
              <span>{{ $t('checkout.payment_fee') }}</span>
              <span class="font-mono">{{ formatMoney(quote.payment_fee_amount) }}</span>
            </div>
            <div
              v-if="quote.discount_code && hasFee(quote.discount_amount ?? '0')"
              class="app-kv app-kv--credit"
            >
              <span>{{ $t('checkout.discount', { code: quote.discount_code }) }}</span>
              <span class="font-mono" data-testid="checkout-quote-discount"
                >−{{ formatMoney(quote.discount_amount ?? '0') }}</span
              >
            </div>
            <div
              v-if="hasFee(quote.deposit_fee_amount)"
              class="app-kv"
              data-testid="checkout-quote-deposit-fee"
            >
              <span>{{ $t('checkout.deposit_fee') }}</span>
              <span class="font-mono">{{ formatMoney(quote.deposit_fee_amount) }}</span>
            </div>
            <div class="app-kv app-kv--total">
              <span>{{
                quote.payment_plan === 'deposit'
                  ? $t('checkout.total_order')
                  : $t('checkout.total_due')
              }}</span>
              <span class="font-mono" data-testid="checkout-quote-total">{{
                formatMoney(quote.total_amount)
              }}</span>
            </div>
            <template v-if="quote.payment_plan === 'deposit'">
              <div class="app-kv summary__due">
                <span>{{ $t('checkout.deposit_now', { pct: Number(quote.deposit_pct) }) }}</span>
                <span class="font-mono" data-testid="checkout-quote-deposit">{{
                  formatMoney(quote.deposit_amount)
                }}</span>
              </div>
              <div class="app-kv">
                <span>{{ $t('checkout.balance_later') }}</span>
                <span class="font-mono">{{ formatMoney(quote.balance_amount) }}</span>
              </div>
            </template>
            <template v-if="hasFee(quote.store_credit_applied)">
              <div class="app-kv app-kv--credit">
                <span>{{ $t('checkout.credit_used') }}</span>
                <span class="font-mono" data-testid="checkout-quote-credit"
                  >−{{ formatMoney(quote.store_credit_applied) }}</span
                >
              </div>
              <div class="app-kv summary__due">
                <span>{{ $t('checkout.due_now') }}</span>
                <span class="font-mono" data-testid="checkout-quote-due">{{
                  formatMoney(quote.amount_due_now)
                }}</span>
              </div>
            </template>
            <p v-if="departureStore.next" class="summary__note" data-testid="checkout-departure">
              <q-icon name="ph:calendar-check" size="14px" />
              {{ $t('checkout.joins_departure', { name: departureStore.next.name }) }}
              <template v-if="nextDelivery"> {{ nextDelivery }}. </template>
            </p>
          </template>
          <template v-else>
            <div class="app-kv app-kv--total">
              <span>{{ $t('checkout.items') }}</span>
              <span class="font-mono">{{ formatMoney(String(cartStore.totalAmount)) }}</span>
            </div>
            <p v-if="isAuthenticated" class="summary__note">
              <q-spinner size="1em" /> {{ $t('checkout.computing') }}
            </p>
          </template>

          <!-- Code promo : validé et chiffré par le backend dans le même devis. -->
          <q-form class="promo" @submit.prevent="applyDiscountCode">
            <q-input
              v-model="discountInput"
              :label="$t('checkout.promo_code')"
              dense
              outlined
              class="promo__input"
              :disable="!isAuthenticated || quoteLoading"
              :error="!!quote?.discount_error"
              :error-message="quote?.discount_error ?? undefined"
              :hint="appliedDiscountHint"
              data-testid="checkout-discount-input"
            >
              <template #append>
                <q-btn
                  v-if="discountCode"
                  flat
                  dense
                  round
                  icon="ph:x"
                  :aria-label="$t('checkout.remove_code')"
                  @click="clearDiscountCode"
                />
              </template>
            </q-input>
            <q-btn
              type="submit"
              outline
              color="primary"
              :label="$t('checkout.apply')"
              class="promo__apply"
              :disable="!isAuthenticated || !discountInput.trim()"
              :loading="quoteLoading"
            />
          </q-form>
        </div>
      </aside>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useMeta } from 'quasar';
import { NOINDEX } from '@/utils/seo';
import { useI18n } from 'vue-i18n';
import { useDepartureLabels } from '@/composables/useDepartureLabels';
import { useRoute } from 'vue-router';
import { countryLabel, orderRef } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import ChoiceList, { type ChoiceOption } from '@/components/ChoiceList.vue';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';
import { useCartStore } from '@/stores/cart';
import { useAuthStore } from '@/stores/auth';
import { useDepartureStore } from '@/stores/departure';
import {
  confirmDocumentUploaded,
  issueDocumentUploadUrl,
  listMyPaymentMethods,
  uploadFileToPresignedUrl,
  type PaymentMethod,
} from '@/api/payments';
import {
  checkoutMyCart,
  getCheckoutQuote,
  getLastLegOptions,
  replaceMyCartItems,
  type CheckoutQuote,
} from '@/api/cart';
import { listMyAddresses, type Address } from '@/api/addresses';
import { PENDING_PAYMENT_KEY, loadPayzenSmartForm } from '@/utils/payzen';

const cartStore = useCartStore();
const authStore = useAuthStore();
const departureStore = useDepartureStore();
const { t, locale } = useI18n();
const { nextDelivery } = useDepartureLabels();
const currencyStore = useCurrencyStore();
const route = useRoute();

useMeta(() => ({ title: t('checkout.meta_title'), meta: NOINDEX }));
// Ordering an issued quote (`?quote=<id>`): its prices and delivery fee apply.
const quoteRequestId = computed(() => {
  const raw = route.query.quote;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return typeof value === 'string' && value.trim() ? value.trim() : null;
});

const loadingMethods = ref(true);
const methods = ref<PaymentMethod[]>([]);
const selectedMethodId = ref<string | null>(null);
const initiating = ref(false);
// Acceptation des CGV — requise avant de pouvoir valider la commande.
const cgvAccepted = ref(false);
const orderPlaced = ref(false);
const formToken = ref<string | null>(null);
const instructions = ref<string | null>(null);
// PayPal : départ vers la page d'approbation après création de la commande.
const redirecting = ref(false);
// Reference of the order just created, shown on the confirmation so the
// customer can quote it before the email arrives (M5).
const placedOrderRef = ref<string | null>(null);
// Departure the order was attached to (the checkout returns its id; the
// store already holds the open one, so no extra request).
const placedDeparture = computed(() =>
  placedDepartureId.value && departureStore.next?.id === placedDepartureId.value
    ? departureStore.next
    : null,
);
const placedDepartureId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
// Payment is tied to a user account (POST /payments/initiate requires auth).
const isAuthenticated = computed(() => authStore.isAuthenticated);

const cartEmpty = computed(() => cartStore.items.length === 0);

// Shipping address. Validated addresses are preferred but we don't hard-block on
// validation (the admin validation flow is a separate decision — A10); the
// backend stores a free-text snapshot regardless.
const addresses = ref<Address[]>([]);
const selectedAddressId = ref<string | null>(null);
const selectedAddress = computed(
  () => addresses.value.find((a) => a.id === selectedAddressId.value) ?? null,
);

// Last-leg delivery modes are driven by the admin's configured routes, not a
// fixed list: they are loaded from the backend so new modes (e.g. sea freight)
// appear automatically with their price.
interface DeliveryChoice {
  value: string;
  label: string;
  icon: string;
  amount: string;
  etaDays: number | null;
}
const deliveryOptions = ref<DeliveryChoice[]>([]);
const selectedDeliveryType = ref<string | null>(null);
// Frais de dédouanement : facturés une fois par expédition, indépendamment du
// mode de livraison et du nombre d'articles.
const customsDeclarationFee = ref('0');

// Devis backend (articles + livraison + dédouanement + frais de paiement) :
// une seule source de vérité pour le total, rechargée à chaque choix.
const quote = ref<CheckoutQuote | null>(null);
const quoteLoading = ref(false);
// Acompte : « full » (tout maintenant) ou « deposit » (acompte + solde à la
// réception), quand le groupe tarifaire du client le propose.
const paymentPlan = ref<'full' | 'deposit'>('full');
const planOptions = computed(() => {
  const q = quote.value;
  const pct = q ? Number(q.deposit_pct) : 0;
  return [
    {
      value: 'full' as const,
      label: t('checkout.plan_full'),
      caption: t('checkout.plan_full_caption'),
    },
    {
      value: 'deposit' as const,
      label: t('checkout.plan_deposit', { pct }),
      caption:
        q && hasFee(q.deposit_fee_amount) && q.payment_plan === 'deposit'
          ? t('checkout.plan_deposit_fee', { fee: formatMoney(q.deposit_fee_amount) })
          : t('checkout.plan_deposit_caption'),
    },
  ];
});
watch(paymentPlan, () => {
  if (!isAuthenticated.value) return;
  void loadQuote();
});
// Store credit (« avoir ») : spent on the amount due now when the customer
// asks; when it covers everything, no payment method is needed.
const useStoreCredit = ref(false);
const creditCoversEverything = computed(
  () =>
    !!quote.value &&
    useStoreCredit.value &&
    hasFee(quote.value.store_credit_applied) &&
    Number.parseFloat(quote.value.amount_due_now) <= 0,
);
watch(useStoreCredit, () => {
  if (!isAuthenticated.value) return;
  void loadQuote();
});
// Montant sur lequel l'éligibilité des moyens de paiement est jugée : le
// total hors frais de paiement (sinon le devis dépend du moyen, qui dépend
// du devis).
const methodsBasis = ref<number | null>(null);

/** Part livraison du devis, hors dédouanement. */
function shippingOnlyAmount(q: CheckoutQuote): number {
  const shipping = Number.parseFloat(q.shipping_fee_amount);
  const customs = Number.parseFloat(q.customs_declaration_fee);
  return (Number.isFinite(shipping) ? shipping : 0) - (Number.isFinite(customs) ? customs : 0);
}

// Code promo : saisi ici, validé par le backend dans le devis puis figé sur
// la commande. Le code appliqué est celui que le dernier devis a accepté.
const discountInput = ref('');
const discountCode = ref<string | null>(null);
const appliedDiscountHint = computed(() => {
  const q = quote.value;
  if (!q?.discount_code) return undefined;
  return t('checkout.discount_hint', {
    label: q.discount_label ?? q.discount_code,
    amount: formatMoney(q.discount_amount ?? '0'),
  });
});

async function applyDiscountCode() {
  const code = discountInput.value.trim();
  if (!code) return;
  discountCode.value = code;
  await loadQuote();
}

function clearDiscountCode() {
  discountInput.value = '';
  discountCode.value = null;
  void loadQuote();
}

async function loadQuote() {
  if (!isAuthenticated.value) return;
  quoteLoading.value = true;
  try {
    const next = await getCheckoutQuote({
      addressId: selectedAddressId.value,
      deliveryType: selectedDeliveryType.value,
      paymentMethodId: selectedMethodId.value,
      discountCode: discountCode.value,
      paymentPlan: paymentPlan.value,
      quoteRequestId: quoteRequestId.value,
      useStoreCredit: useStoreCredit.value,
    });
    // A refused code is reported by the quote (the amounts stay valid
    // without it); it must not be sent to the checkout either.
    if (next.discount_error) discountCode.value = null;
    quote.value = next;
    // The backend has the last word (an imposed deposit, or none offered).
    if (next.payment_plan === 'deposit' || next.payment_plan === 'full') {
      paymentPlan.value = next.payment_plan;
    }
    const basis =
      Number.parseFloat(next.subtotal_amount) + Number.parseFloat(next.shipping_fee_amount);
    if (Number.isFinite(basis) && basis !== methodsBasis.value) {
      methodsBasis.value = basis;
      await loadMethods(basis);
    }
  } catch {
    // Le devis est indispensable : sans lui le bouton reste grisé et le
    // client voit le montant des articles seuls. Les moyens de paiement
    // restent proposés (sur le montant des articles) pour ne pas figer
    // l'écran sur un spinner.
    quote.value = null;
    if (methodsBasis.value === null) {
      await loadMethods(cartStore.totalAmount);
    }
  } finally {
    quoteLoading.value = false;
  }
}

async function loadMethods(basis: number) {
  loadingMethods.value = true;
  try {
    // Eligibility-filtered list (price group + max_amount vs amount to pay).
    // The server re-checks eligibility at POST /cart/checkout regardless.
    const available = await listMyPaymentMethods(basis);
    methods.value = available.sort((a, b) => a.sort_order - b.sort_order);
    if (!methods.value.some((m) => m.id === selectedMethodId.value)) {
      selectedMethodId.value = methods.value[0]?.id ?? null;
    }
  } catch {
    errorMessage.value = t('checkout.methods_failed');
  } finally {
    loadingMethods.value = false;
  }
}

function iconForMode(mode: string): string {
  if (mode === 'pickup') return 'ph:storefront';
  if (mode === 'air_freight') return 'ph:airplane-tilt';
  if (mode === 'sea_freight') return 'ph:boat';
  return 'ph:truck';
}
function prettifyMode(mode: string): string {
  return mode.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
function deliveryPriceLabel(amount: string): string {
  const n = Number.parseFloat(amount);
  if (!Number.isFinite(n)) return '';
  return n > 0 ? `+ ${formatMoney(amount)}` : t('checkout.free');
}

function formatAddress(a: Address): string {
  return [a.street, `${a.postal_code} ${a.city}`.trim(), a.state, a.country]
    .filter((part) => !!part && String(part).trim().length > 0)
    .join(', ');
}

// Document-validated (Bon de commande) upload state.
const pendingPaymentId = ref<string | null>(null);
const selectedFile = ref<File | null>(null);
const uploading = ref(false);
const uploadDone = ref(false);
const uploadError = ref<string | null>(null);

const selectedMethod = computed(
  () => methods.value.find((m) => m.id === selectedMethodId.value) ?? null,
);
const needsUpload = computed(
  () =>
    selectedMethod.value?.requires_document_upload === true ||
    selectedMethod.value?.provider_code === 'document',
);

/** Montants du panier et du devis : dans la devise de facturation. */
function formatMoney(raw: string): string {
  return orderMoney(raw, quote.value?.currency, currencyStore.reference);
}

function hasFee(fee: string): boolean {
  return Number.parseFloat(fee) > 0;
}

function methodIcon(providerCode: string): string {
  if (providerCode === 'payzen') return 'ph:credit-card';
  if (providerCode === 'paypal') return 'ph:paypal-logo';
  if (providerCode === 'manual_transfer') return 'ph:bank';
  if (providerCode === 'manual_check') return 'ph:money';
  if (providerCode === 'manual_cash') return 'ph:coins';
  if (providerCode.startsWith('po_') || providerCode === 'document') return 'ph:file-text';
  return 'ph:wallet';
}

// --- Options des listes de choix -------------------------------------------
const addressChoices = computed<ChoiceOption[]>(() =>
  addresses.value.map((a) => ({
    value: a.id,
    title: a.street,
    caption: `${a.postal_code} ${a.city}, ${countryLabel(a.country)}`,
    icon: 'ph:map-pin',
    testid: `checkout-address-${a.id}`,
  })),
);

const deliveryChoices = computed<ChoiceOption[]>(() =>
  deliveryOptions.value.map((d) => ({
    value: d.value,
    title: d.label,
    caption: d.etaDays != null ? t('checkout.eta', { n: d.etaDays }) : null,
    icon: d.icon,
    aside: deliveryPriceLabel(d.amount),
    testid: `checkout-delivery-${d.value}`,
  })),
);

const planChoices = computed<ChoiceOption<'full' | 'deposit'>[]>(() =>
  planOptions.value.map((p) => ({
    value: p.value,
    title: p.label,
    caption: p.caption,
    testid: `checkout-plan-${p.value}`,
  })),
);

// A method the shop excluded from deposits is not offered when paying one.
const usableMethods = computed(() =>
  paymentPlan.value === 'deposit'
    ? methods.value.filter((m) => m.deposit_allowed !== false)
    : methods.value,
);

watch(usableMethods, (usable) => {
  if (!usable.some((m) => m.id === selectedMethodId.value)) {
    selectedMethodId.value = usable[0]?.id ?? null;
  }
});

const methodChoices = computed<ChoiceOption[]>(() =>
  usableMethods.value.map((m) => ({
    value: m.id,
    title: m.name,
    caption: m.description,
    icon: methodIcon(m.provider_code),
    aside: hasFee(m.fee) ? `+ ${formatMoney(m.fee)}` : null,
    testid: `checkout-method-${m.provider_code}`,
  })),
);

/** Numéro d'étape : la livraison et le règlement n'apparaissent pas toujours. */
function stepNumber(step: 'plan' | 'payment'): number {
  let n = 1;
  if (deliveryOptions.value.length > 0) n += 1;
  if (step === 'plan') return n + 1;
  if (quote.value?.deposit_available) n += 1;
  return n + 1;
}

const submitLabel = computed(() => {
  const q = quote.value;
  if (!q) return t('checkout.validate');
  const due = hasFee(q.store_credit_applied)
    ? q.amount_due_now
    : q.payment_plan === 'deposit'
      ? q.deposit_amount
      : q.total_amount;
  if (!hasFee(due) || !paysByCard.value) return t('checkout.validate');
  return t('checkout.pay_amount', { amount: formatMoney(due) });
});

/** Carte ou PayPal : le paiement se fait tout de suite, chez le prestataire. */
const paysByCard = computed(
  () =>
    !creditCoversEverything.value &&
    ['payzen', 'paypal'].includes(selectedMethod.value?.provider_code ?? ''),
);

onMounted(async () => {
  await cartStore.loadCart();
  if (!isAuthenticated.value) {
    loadingMethods.value = false;
    return;
  }
  // The storefront cart is client-side: mirror it into the backend cart so
  // the delivery options and the quote are computed on what is being bought.
  // Ordering an issued quote: the backend cart was just loaded from the quote
  // at the quoted prices (« Commander ce devis »), it must not be overwritten.
  if (!quoteRequestId.value) {
    try {
      await syncCartToBackend();
    } catch {
      // The checkout re-syncs before ordering; the quote will then catch up.
    }
  }

  // Load the user's addresses; pre-select a validated one if available, else the first.
  try {
    addresses.value = await listMyAddresses();
    const preferred = addresses.value.find((a) => a.is_validated) ?? addresses.value[0] ?? null;
    selectedAddressId.value = preferred?.id ?? null;
  } catch {
    // Non-blocking: the address selector shows an empty state with guidance.
  }

  // Priced last-leg delivery options for the current cart and the pre-selected
  // address (the watcher below reloads them on address change), then the
  // quote — which also loads the payment methods eligible for that amount.
  await loadDeliveryOptions();
  await loadQuote();
});

// Delivery modes depend on the destination (île → archipel → pays) of the
// selected address: reload them whenever the customer picks another address.
async function loadDeliveryOptions() {
  try {
    const res = await getLastLegOptions(selectedAddressId.value);
    customsDeclarationFee.value = String(res.customs_declaration_fee ?? '0');
    deliveryOptions.value = res.options.map((o) => ({
      value: o.delivery_type,
      label: o.label || prettifyMode(o.delivery_type),
      icon: iconForMode(o.delivery_type),
      amount: o.amount,
      etaDays: o.eta_days,
    }));
    // Keep the current choice when the new destination still offers it.
    if (!deliveryOptions.value.some((d) => d.value === selectedDeliveryType.value)) {
      selectedDeliveryType.value = deliveryOptions.value[0]?.value ?? null;
    }
  } catch {
    // Non-blocking: the delivery section is hidden if options can't be loaded.
    deliveryOptions.value = [];
    selectedDeliveryType.value = null;
    customsDeclarationFee.value = '0';
  }
}

watch(selectedAddressId, async () => {
  if (!isAuthenticated.value) return;
  await loadDeliveryOptions();
  await loadQuote();
});
watch(selectedDeliveryType, () => {
  if (!isAuthenticated.value) return;
  void loadQuote();
});
watch(selectedMethodId, () => {
  if (!isAuthenticated.value) return;
  void loadQuote();
});

async function startPayment() {
  const method = methods.value.find((m) => m.id === selectedMethodId.value) ?? null;
  if (!method && !creditCoversEverything.value) return;
  if (!isAuthenticated.value) {
    errorMessage.value = t('checkout.must_login');
    return;
  }
  if (!selectedAddress.value) {
    errorMessage.value = t('checkout.choose_address');
    return;
  }

  initiating.value = true;
  errorMessage.value = null;

  try {
    const returnUrl = `${window.location.origin}/paiement/retour`;

    // 1. The storefront cart is client-side — mirror it into the backend cart
    //    so the order can be created from it (a quote rebuilds it server-side).
    if (!quoteRequestId.value) await syncCartToBackend();

    // 2. Single call: create the order AND run the provider initiation in one
    //    transaction (empties the backend cart, publishes order.created). No
    //    separate /payments/initiate — one order, one payment.
    // No shipping_preference here: the delivery mode chosen above is the only
    // last leg; a preference on top of it used to bill a second one.
    const checkout = await checkoutMyCart({
      delivery_type: selectedDeliveryType.value,
      shipping_address: formatAddress(selectedAddress.value),
      shipping_address_id: selectedAddressId.value,
      payment_method_id: creditCoversEverything.value ? null : (method?.id ?? null),
      return_url: returnUrl,
      cgv_accepted: cgvAccepted.value,
      discount_code: quote.value?.discount_code ?? null,
      payment_plan: paymentPlan.value,
      quote_request_id: quoteRequestId.value,
      use_store_credit: useStoreCredit.value,
    });
    orderPlaced.value = true;
    placedOrderRef.value = orderRef(checkout.order_number, checkout.order_id);
    placedDepartureId.value = checkout.grouped_departure_id ?? null;

    // 3. Clear the local cart now that the order exists.
    cartStore.clearCart();

    // Card (Payzen API): render the SmartForm and poll status on return.
    if (checkout.form_token && checkout.server_url && checkout.public_key) {
      localStorage.setItem(PENDING_PAYMENT_KEY, checkout.payment_id);
      formToken.value = checkout.form_token;
      // Carry the payment id in the redirect URL, not only in localStorage.
      // 3-D Secure often finishes in the bank's app or another browser, and the
      // customer then lands on the return page with an empty local store —
      // which used to greet a successful payment with "no pending transaction".
      await loadPayzenSmartForm({
        serverUrl: checkout.server_url,
        publicKey: checkout.public_key,
        token: checkout.form_token,
        returnUrl: `${returnUrl}?payment=${encodeURIComponent(checkout.payment_id)}`,
        language: locale.value,
      });
      return;
    }

    // PayPal: the customer approves on PayPal's page and comes back to
    // /paiement/retour?payment=…&provider=paypal, where the shop captures it.
    if (checkout.redirect_url) {
      localStorage.setItem(PENDING_PAYMENT_KEY, checkout.payment_id);
      redirecting.value = true;
      window.location.assign(checkout.redirect_url);
      return;
    }

    // Manual (chèque/virement) or document-validated (BC): show the payment
    // instructions; the order is recorded and awaits validation. The payment id
    // is kept so a Bon de commande can be uploaded for document providers.
    if (checkout.instructions) {
      instructions.value = checkout.instructions;
      pendingPaymentId.value = checkout.payment_id;
      return;
    }

    // Settled by the store credit alone: nothing to pay, the order is placed.
    if (
      Number.parseFloat(String(checkout.amount_due_now ?? '0')) <= 0 &&
      hasFee(String(checkout.store_credit_applied ?? '0'))
    ) {
      instructions.value = t('checkout.paid_by_credit', {
        amount: formatMoney(String(checkout.store_credit_applied)),
      });
      return;
    }

    errorMessage.value = t('checkout.method_unavailable');
  } catch (err: unknown) {
    // The backend refuses to bill a price that moved since the line was added.
    // Adopt the prices it just returned so the recap shows what is actually
    // being asked, then let the customer confirm the new total.
    const drifted = extractPriceDrift(err);
    if (drifted) {
      cartStore.applyServerPrices(drifted);
    }
    errorMessage.value = apiErrorMessage(err) ?? t('checkout.failed');
  } finally {
    initiating.value = false;
  }
}

type PriceDriftItem = { product_id: string; current_unit_price: string };

/** Read the per-line new prices carried by a `cart.price.changed` refusal. */
function extractPriceDrift(err: unknown): PriceDriftItem[] | null {
  if (!err || typeof err !== 'object' || !('response' in err)) return null;
  const data = (err as { response?: { data?: unknown } }).response?.data;
  if (typeof data !== 'object' || data === null) return null;
  const errorObj = (data as { error?: { code?: unknown; details?: unknown } }).error;
  if (!errorObj || errorObj.code !== 'cart.price.changed') return null;
  const items = (errorObj.details as { items?: unknown } | undefined)?.items;
  if (!Array.isArray(items)) return null;
  return items.filter(
    (row): row is PriceDriftItem =>
      typeof row === 'object' &&
      row !== null &&
      typeof (row as PriceDriftItem).product_id === 'string' &&
      typeof (row as PriceDriftItem).current_unit_price === 'string',
  );
}

/**
 * Mirror the client-side cart into the backend cart, atomically.
 *
 * This used to be a clear followed by one POST per line. Nothing made that
 * sequence transactional: a failure in the middle left a truncated backend
 * cart, and the checkout that followed ordered it as if it were complete.
 */
async function syncCartToBackend() {
  await replaceMyCartItems({
    items: cartStore.detailedItems.map(({ item }) => ({
      product_id: item.product_id,
      quantity: item.quantity,
    })),
  });
}

async function uploadDocument() {
  const file = selectedFile.value;
  if (!file || !pendingPaymentId.value) return;
  uploading.value = true;
  uploadError.value = null;
  try {
    const mimetype = file.type || 'application/octet-stream';
    const intent = await issueDocumentUploadUrl(pendingPaymentId.value, {
      filename: file.name,
      mimetype,
    });
    await uploadFileToPresignedUrl(intent, file);
    await confirmDocumentUploaded(pendingPaymentId.value, {
      fileKey: intent.file_key,
      filename: file.name,
      mimetype,
    });
    uploadDone.value = true;
  } catch (err) {
    uploadError.value = apiErrorMessage(err) ?? t('checkout.po_failed');
  } finally {
    uploading.value = false;
  }
}
</script>

<style scoped lang="scss">
.checkout__back {
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

.checkout__title {
  margin-bottom: 32px;
}

.checkout__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 64px;
  align-items: start;

  &--done {
    grid-template-columns: minmax(0, 720px);
  }

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
  }
}

.checkout__notice {
  margin-bottom: 20px;
}

.checkout__skeleton {
  margin-bottom: 8px;
  border-radius: 8px;
}

.step + .step {
  margin-top: 40px;
}

.step__title {
  margin: 0 0 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.step__num {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--n-ink);
  color: var(--n-on-ink);
  font-size: 13px;
  font-weight: 500;
}

.step__empty {
  padding: 28px 16px;
}

.step__link {
  margin-top: 10px;
  display: inline-block;
}

.credit-toggle {
  margin-bottom: 12px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.credit-toggle__text {
  flex-grow: 1;
  font-size: 14px;
}

.checkout__confirm {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid var(--n-line);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.checkout__cgv {
  font-size: 14px;

  a {
    color: inherit;
    text-underline-offset: 3px;
  }
}

.checkout__submit {
  min-height: 52px;
  font-size: 16px;
}

.checkout__secure {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--n-ink-3);
}

.checkout__card-form {
  max-width: 480px;
}

.checkout__aside {
  position: sticky;
  top: 88px;

  @media (max-width: 1023px) {
    position: static;
    order: -1;
  }
}

.summary__title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.summary__lines {
  margin: 0 0 16px;
  padding: 0 0 16px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--n-line-2);
  font-size: 14px;

  li {
    display: flex;
    justify-content: space-between;
    gap: 16px;
  }
}

.summary__line-name {
  min-width: 0;
}

.summary__qty {
  margin-right: 4px;
  color: var(--n-ink-3);
}

.summary__due {
  color: var(--n-ink);
  font-weight: 500;
}

.summary__note {
  margin: 14px 0 0;
  display: flex;
  gap: 6px;
  font-size: 13px;
  color: var(--n-ink-2);
}

.promo {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--n-line-2);
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.promo__input {
  flex-grow: 1;
}

.promo__apply {
  min-height: 40px;
}

.confirmation__head {
  display: flex;
  gap: 16px;
}

.confirmation__icon {
  flex-shrink: 0;
  color: var(--n-ok);
}

.confirmation__ref {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.confirmation__text {
  margin: 6px 0 0;
  color: var(--n-ink-2);
}

.confirmation__instructions {
  margin-top: 32px;
}

.confirmation__body {
  margin: 0;
  white-space: pre-line;
  line-height: 1.6;
}

.confirmation__actions {
  margin-top: 32px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
