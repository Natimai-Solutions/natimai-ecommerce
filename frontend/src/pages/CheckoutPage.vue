<template>
  <q-page class="checkout-page q-pa-md">
    <div class="row q-mb-md items-center">
      <div class="col">
        <h1 class="text-h5 q-my-none">Paiement sécurisé</h1>
      </div>
      <div class="col-auto">
        <q-btn
          flat
          color="primary"
          icon="arrow_back"
          label="Retour au panier"
          :to="{ name: 'cart' }"
        />
      </div>
    </div>

    <!-- Cart empty guard (not while a payment is already in progress) -->
    <q-banner v-if="cartEmpty && !orderPlaced" class="bg-orange-1 text-orange-10 q-mb-md" rounded>
      <template #avatar><q-icon name="warning_amber" /></template>
      Votre panier est vide.
      <template #action>
        <q-btn flat label="Voir le catalogue" :to="{ name: 'catalogue' }" />
      </template>
    </q-banner>

    <template v-else>
      <div class="row q-col-gutter-lg">
        <!-- Order summary (hidden once the order is placed and the cart cleared) -->
        <div v-if="!orderPlaced" class="col-12 col-md-5 col-lg-4">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 text-weight-medium q-mb-sm">Récapitulatif</div>
              <q-list dense>
                <q-item
                  v-for="{ item, product } in cartStore.detailedItems"
                  :key="item.id"
                  class="q-px-none"
                >
                  <q-item-section>
                    <q-item-label>{{ product?.name ?? item.product_id }}</q-item-label>
                    <q-item-label caption>Qté {{ item.quantity }}</q-item-label>
                  </q-item-section>
                  <q-item-section side>
                    <q-item-label>{{ formatMoney(item.line_total) }}</q-item-label>
                  </q-item-section>
                </q-item>
              </q-list>
              <q-separator class="q-my-sm" />
              <div class="row justify-between text-weight-bold">
                <span>Total</span>
                <span>{{ formatMoney(String(cartStore.totalAmount)) }}</span>
              </div>
            </q-card-section>
          </q-card>
        </div>

        <!-- Payment -->
        <div :class="orderPlaced ? 'col-12' : 'col-12 col-md-7 col-lg-8'">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 text-weight-medium q-mb-md">Paiement</div>

              <!-- Error banner -->
              <q-banner v-if="errorMessage" class="bg-red-1 text-red-9 q-mb-md" rounded>
                <template #avatar><q-icon name="error_outline" /></template>
                {{ errorMessage }}
              </q-banner>

              <!-- Loading payment methods -->
              <div v-if="loadingMethods" class="text-center q-pa-lg">
                <q-spinner color="primary" size="2em" />
                <div class="text-caption q-mt-sm">Chargement des moyens de paiement…</div>
              </div>

              <!-- Authentication required: payment is tied to a user account -->
              <template v-else-if="!isAuthenticated">
                <q-banner class="bg-blue-1 text-blue-10 q-mb-md" rounded>
                  <template #avatar><q-icon name="lock" /></template>
                  Vous devez être connecté pour finaliser votre paiement.
                </q-banner>
                <q-btn
                  color="primary"
                  icon="login"
                  label="Se connecter"
                  size="lg"
                  class="full-width"
                  :to="{ name: 'login', query: { redirect: '/checkout' } }"
                />
              </template>

              <!-- No method available -->
              <q-banner v-else-if="methods.length === 0" class="bg-orange-1 text-orange-10" rounded>
                <template #avatar><q-icon name="info" /></template>
                Aucun moyen de paiement n'est disponible pour votre compte. Veuillez contacter notre
                équipe.
              </q-banner>

              <template v-else>
                <!-- Manual / document payment confirmation (chèque, virement, BC) -->
                <template v-if="instructions">
                  <q-banner class="bg-green-1 text-green-9 q-mb-md" rounded>
                    <template #avatar><q-icon name="check_circle" /></template>
                    Votre demande de paiement a bien été enregistrée.
                  </q-banner>
                  <div class="text-body2 q-mb-md" style="white-space: pre-line">
                    {{ instructions }}
                  </div>

                  <!-- Bon de commande (BC) : téléversement de la pièce -->
                  <template v-if="needsUpload && !uploadDone">
                    <div class="text-caption text-grey-7 q-mb-xs">
                      Joignez votre bon de commande pour permettre la validation de la commande.
                    </div>
                    <q-banner v-if="uploadError" class="bg-red-1 text-red-9 q-mb-sm" rounded dense>
                      {{ uploadError }}
                    </q-banner>
                    <q-file
                      v-model="selectedFile"
                      outlined
                      dense
                      label="Bon de commande (PDF, JPG, PNG)"
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/*"
                      :max-file-size="20 * 1024 * 1024"
                    >
                      <template #prepend><q-icon name="attach_file" /></template>
                    </q-file>
                    <q-btn
                      color="primary"
                      icon="upload_file"
                      label="Envoyer le bon de commande"
                      class="full-width q-mt-sm"
                      :loading="uploading"
                      :disable="uploading || !selectedFile"
                      @click="uploadDocument"
                    />
                  </template>

                  <q-banner v-else-if="uploadDone" class="bg-green-1 text-green-9 q-mb-md" rounded>
                    <template #avatar><q-icon name="task_alt" /></template>
                    Bon de commande reçu — il sera vérifié par notre équipe avant validation.
                  </q-banner>

                  <q-btn
                    v-if="!needsUpload || uploadDone"
                    color="primary"
                    icon="receipt_long"
                    label="Voir mes commandes"
                    class="full-width q-mt-sm"
                    :to="{ name: 'account', query: { tab: 'orders' } }"
                  />
                </template>

                <!-- Method selection + initiate -->
                <template v-else-if="!formToken">
                  <!-- Shipping address (validated addresses only) -->
                  <div class="text-subtitle2 text-weight-medium q-mb-sm">Adresse de livraison</div>
                  <q-banner
                    v-if="addresses.length === 0"
                    class="bg-orange-1 text-orange-10 q-mb-md"
                    rounded
                    dense
                  >
                    <template #avatar><q-icon name="location_off" /></template>
                    Aucune adresse enregistrée. Ajoutez-en une depuis « Mon compte ».
                    <template #action>
                      <q-btn
                        flat
                        dense
                        no-caps
                        label="Mes adresses"
                        :to="{ name: 'account', query: { tab: 'addresses' } }"
                      />
                    </template>
                  </q-banner>
                  <q-list v-else bordered separator class="rounded-borders q-mb-md">
                    <q-item
                      v-for="a in addresses"
                      :key="a.id"
                      v-ripple
                      clickable
                      :active="selectedAddressId === a.id"
                      active-class="bg-blue-1"
                      @click="selectedAddressId = a.id"
                    >
                      <q-item-section avatar>
                        <q-radio v-model="selectedAddressId" :val="a.id" />
                      </q-item-section>
                      <q-item-section avatar>
                        <q-icon name="place" color="primary" />
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ a.street }}</q-item-label>
                        <q-item-label caption>
                          {{ a.postal_code }} {{ a.city }} — {{ countryLabel(a.country) }}
                        </q-item-label>
                      </q-item-section>
                      <q-item-section side>
                        <q-chip
                          v-if="a.is_validated"
                          dense
                          size="sm"
                          color="green"
                          text-color="white"
                          icon="verified"
                          label="Validée"
                        />
                        <q-chip
                          v-else
                          dense
                          size="sm"
                          color="orange-2"
                          text-color="orange-10"
                          label="Non validée"
                        />
                      </q-item-section>
                    </q-item>
                  </q-list>

                  <template v-if="deliveryOptions.length > 0">
                    <div class="text-subtitle2 text-weight-medium q-mb-sm">Mode de livraison</div>
                    <q-list bordered separator class="rounded-borders q-mb-md">
                      <q-item
                        v-for="d in deliveryOptions"
                        :key="d.value"
                        v-ripple
                        clickable
                        :active="selectedDeliveryType === d.value"
                        active-class="bg-blue-1"
                        @click="selectedDeliveryType = d.value"
                      >
                        <q-item-section avatar>
                          <q-radio v-model="selectedDeliveryType" :val="d.value" />
                        </q-item-section>
                        <q-item-section avatar>
                          <q-icon :name="d.icon" color="primary" />
                        </q-item-section>
                        <q-item-section>
                          <q-item-label>{{ d.label }}</q-item-label>
                          <q-item-label v-if="d.etaDays != null" caption>
                            Livraison estimée ~{{ d.etaDays }} j
                          </q-item-label>
                        </q-item-section>
                        <q-item-section v-if="deliveryPriceLabel(d.amount)" side>
                          <q-item-label class="text-weight-medium text-primary">
                            {{ deliveryPriceLabel(d.amount) }}
                          </q-item-label>
                        </q-item-section>
                      </q-item>
                    </q-list>
                  </template>

                  <div class="text-subtitle2 text-weight-medium q-mb-sm">Moyen de paiement</div>
                  <q-list bordered separator class="rounded-borders q-mb-md">
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
                      <q-item-section avatar>
                        <q-icon :name="methodIcon(m.provider_code)" color="primary" />
                      </q-item-section>
                      <q-item-section>
                        <q-item-label>{{ m.name }}</q-item-label>
                        <q-item-label v-if="m.description" caption>{{
                          m.description
                        }}</q-item-label>
                      </q-item-section>
                      <q-item-section v-if="hasFee(m.fee)" side>
                        <q-item-label caption>+ {{ formatMoney(m.fee) }} de frais</q-item-label>
                      </q-item-section>
                    </q-item>
                  </q-list>

                  <q-btn
                    color="primary"
                    icon="check_circle"
                    label="Valider la commande"
                    size="lg"
                    class="full-width"
                    :loading="initiating"
                    :disable="
                      initiating ||
                      !selectedMethodId ||
                      !selectedAddressId ||
                      (deliveryOptions.length > 0 && !selectedDeliveryType)
                    "
                    @click="startPayment"
                  />
                </template>

                <!-- Payzen SmartForm container -->
                <div v-show="formToken">
                  <div id="kr-smart-form-container" />
                </div>
              </template>
            </q-card-section>
          </q-card>
        </div>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { countryLabel, formatXpf } from '@app/utils';
import { useCartStore } from 'src/stores/cart';
import { useAuthStore } from 'src/stores/auth';
import {
  confirmDocumentUploaded,
  issueDocumentUploadUrl,
  listMyPaymentMethods,
  uploadFileToPresignedUrl,
  type PaymentMethod,
} from 'src/api/payments';
import { addCartItem, checkoutMyCart, clearMyCart, getLastLegOptions } from 'src/api/cart';
import { listMyAddresses, type Address } from 'src/api/addresses';

const PENDING_PAYMENT_KEY = 'payzen.pending_payment_id';

const cartStore = useCartStore();
const authStore = useAuthStore();

const loadingMethods = ref(true);
const methods = ref<PaymentMethod[]>([]);
const selectedMethodId = ref<string | null>(null);
const initiating = ref(false);
const orderPlaced = ref(false);
const formToken = ref<string | null>(null);
const instructions = ref<string | null>(null);
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

function iconForMode(mode: string): string {
  if (mode === 'pickup') return 'store';
  if (mode === 'air_freight') return 'flight';
  if (mode === 'sea_freight') return 'directions_boat';
  return 'local_shipping';
}
function prettifyMode(mode: string): string {
  return mode.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
function deliveryPriceLabel(amount: string): string {
  const n = Number.parseFloat(amount);
  if (!Number.isFinite(n)) return '';
  return n > 0 ? `+ ${formatMoney(amount)}` : 'Offert';
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

function formatMoney(raw: string): string {
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? formatXpf(n) : raw;
}

function hasFee(fee: string): boolean {
  return Number.parseFloat(fee) > 0;
}

function methodIcon(providerCode: string): string {
  if (providerCode === 'payzen') return 'credit_card';
  if (providerCode === 'manual') return 'account_balance';
  if (providerCode === 'document') return 'description';
  return 'payments';
}

onMounted(async () => {
  await cartStore.loadCart();
  if (!isAuthenticated.value) {
    loadingMethods.value = false;
    return;
  }
  try {
    // Eligibility-filtered list (price group + max_amount vs cart total). The
    // server re-checks eligibility at POST /cart/checkout regardless.
    const available = await listMyPaymentMethods(cartStore.totalAmount);
    methods.value = available.sort((a, b) => a.sort_order - b.sort_order);
    selectedMethodId.value = methods.value[0]?.id ?? null;
  } catch {
    errorMessage.value = 'Impossible de charger les moyens de paiement.';
  } finally {
    loadingMethods.value = false;
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
  // address (the watcher below reloads them on address change).
  await loadDeliveryOptions();
});

// Delivery modes depend on the destination (île → archipel → pays) of the
// selected address: reload them whenever the customer picks another address.
async function loadDeliveryOptions() {
  try {
    const res = await getLastLegOptions(selectedAddressId.value);
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
  }
}

watch(selectedAddressId, () => {
  if (!isAuthenticated.value) return;
  void loadDeliveryOptions();
});

async function startPayment() {
  const method = methods.value.find((m) => m.id === selectedMethodId.value);
  if (!method) return;
  if (!isAuthenticated.value) {
    errorMessage.value = 'Vous devez être connecté pour payer.';
    return;
  }
  if (!selectedAddress.value) {
    errorMessage.value = 'Veuillez sélectionner une adresse de livraison validée.';
    return;
  }

  initiating.value = true;
  errorMessage.value = null;

  try {
    const returnUrl = `${window.location.origin}/paiement/retour`;

    // 1. The storefront cart is client-side — mirror it into the backend cart
    //    so the order can be created from it.
    await syncCartToBackend();

    // 2. Single call: create the order AND run the provider initiation in one
    //    transaction (empties the backend cart, publishes order.created). No
    //    separate /payments/initiate — one order, one payment.
    const checkout = await checkoutMyCart({
      shipping_preference: 'fastest',
      delivery_type: selectedDeliveryType.value,
      payment_fee_amount: '0.00',
      shipping_address: formatAddress(selectedAddress.value),
      shipping_address_id: selectedAddressId.value,
      payment_method_id: method.id,
      return_url: returnUrl,
    });
    orderPlaced.value = true;

    // 3. Clear the local cart now that the order exists.
    cartStore.clearCart();

    // Card (Payzen API): render the SmartForm and poll status on return.
    if (checkout.form_token && checkout.server_url && checkout.public_key) {
      localStorage.setItem(PENDING_PAYMENT_KEY, checkout.payment_id);
      formToken.value = checkout.form_token;
      await loadPayzenSmartForm({
        serverUrl: checkout.server_url,
        publicKey: checkout.public_key,
        token: checkout.form_token,
        returnUrl,
      });
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

    errorMessage.value =
      "Le moyen de paiement sélectionné n'est pas disponible pour le moment. Veuillez réessayer.";
  } catch (err: unknown) {
    errorMessage.value =
      extractError(err) ?? 'Une erreur est survenue lors de la finalisation de la commande.';
  } finally {
    initiating.value = false;
  }
}

/** Mirror the client-side cart into the backend cart (reset then re-add). */
async function syncCartToBackend() {
  await clearMyCart();
  for (const { item } of cartStore.detailedItems) {
    await addCartItem({ product_id: item.product_id, quantity: item.quantity });
  }
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
    uploadError.value =
      extractError(err) ?? "Échec de l'envoi du bon de commande. Veuillez réessayer.";
  } finally {
    uploading.value = false;
  }
}

function extractError(err: unknown): string | null {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
  }
  return null;
}

interface SmartFormOptions {
  serverUrl: string;
  publicKey: string;
  token: string;
  returnUrl: string;
}

function loadPayzenSmartForm({
  serverUrl,
  publicKey,
  token,
  returnUrl,
}: SmartFormOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById('kr-payzen-script');
    if (existing) existing.remove();

    const script = document.createElement('script');
    script.id = 'kr-payzen-script';
    script.src = `${serverUrl}/static/js/krypton-client/V4.0/ext/smartform.min.js`;
    script.setAttribute('kr-public-key', publicKey);
    script.setAttribute('kr-post-url-success', returnUrl);
    script.setAttribute('kr-language', 'fr-FR');
    script.onload = () => {
      const container = document.getElementById('kr-smart-form-container');
      if (container) {
        container.innerHTML = `<div class="kr-smart-form" kr-form-token="${token}"></div>`;
      }
      resolve();
    };
    script.onerror = () => reject(new Error('Impossible de charger le script Payzen'));
    document.head.appendChild(script);
  });
}
</script>
