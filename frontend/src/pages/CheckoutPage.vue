<template>
  <q-page class="checkout-page q-pa-md">
    <div class="row q-mb-md items-center">
      <div class="col">
        <h1 class="text-h5 q-my-none">Paiement sécurisé</h1>
      </div>
      <div class="col-auto">
        <q-btn flat color="primary" icon="arrow_back" label="Retour au panier" :to="{ name: 'cart' }" />
      </div>
    </div>

    <!-- Cart empty guard -->
    <q-banner v-if="cartEmpty" class="bg-orange-1 text-orange-10 q-mb-md" rounded>
      <template #avatar><q-icon name="warning_amber" /></template>
      Votre panier est vide.
      <template #action>
        <q-btn flat label="Voir le catalogue" :to="{ name: 'catalogue' }" />
      </template>
    </q-banner>

    <template v-else>
      <div class="row q-col-gutter-lg">
        <!-- Order summary -->
        <div class="col-12 col-md-5 col-lg-4">
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

        <!-- Payment form -->
        <div class="col-12 col-md-7 col-lg-8">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 text-weight-medium q-mb-md">Moyen de paiement</div>

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

              <!-- No Payzen method configured -->
              <q-banner
                v-else-if="!payzenMethod"
                class="bg-orange-1 text-orange-10"
                rounded
              >
                <template #avatar><q-icon name="info" /></template>
                Aucun moyen de paiement par carte bancaire n'est disponible pour le moment.
                Veuillez contacter notre équipe.
              </q-banner>

              <!-- Authentication required: a CB payment is tied to a user account -->
              <template v-else-if="!isAuthenticated">
                <q-banner class="bg-blue-1 text-blue-10 q-mb-md" rounded>
                  <template #avatar><q-icon name="lock" /></template>
                  Vous devez être connecté pour payer par carte bancaire.
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

              <!-- Initiate button (before form is loaded) -->
              <template v-else-if="!formToken">
                <div class="text-body2 text-grey-8 q-mb-md">
                  {{ payzenMethod.name }}
                  <span v-if="payzenMethod.description" class="text-caption"> — {{ payzenMethod.description }}</span>
                </div>
                <q-btn
                  color="primary"
                  icon="lock"
                  label="Procéder au paiement"
                  size="lg"
                  class="full-width"
                  :loading="initiating"
                  :disable="initiating"
                  @click="startPayment"
                />
              </template>

              <!-- Payzen SmartForm container -->
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
import { computed, onMounted, ref } from 'vue'
import { formatXpf } from '@app/utils'
import { useCartStore } from 'src/stores/cart'
import { useAuthStore } from 'src/stores/auth'
import {
  initiatePayment,
  listMyPaymentMethods,
  listPaymentMethods,
  type PaymentMethod,
} from 'src/api/payments'

const PENDING_PAYMENT_KEY = 'payzen.pending_payment_id'

const cartStore = useCartStore()
const authStore = useAuthStore()

const loadingMethods = ref(true)
const payzenMethod = ref<PaymentMethod | null>(null)
const initiating = ref(false)
const formToken = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
// CB payment is tied to a user account (POST /payments/initiate requires auth).
const isAuthenticated = computed(() => authStore.isAuthenticated)

const cartEmpty = computed(() => cartStore.items.length === 0)

function formatMoney(raw: string): string {
  const n = Number.parseFloat(raw)
  return Number.isFinite(n) ? formatXpf(n) : raw
}

onMounted(async () => {
  await cartStore.loadCart()
  try {
    // Authenticated users get the eligibility-filtered list (price group +
    // max_amount vs cart total); guests fall back to the public catalogue so the
    // "Se connecter" prompt can still render. The server re-checks eligibility
    // at POST /payments/initiate regardless.
    const methods = isAuthenticated.value
      ? await listMyPaymentMethods(cartStore.totalAmount)
      : await listPaymentMethods()
    payzenMethod.value =
      methods
        .filter((m) => m.provider_code === 'payzen' && !m.requires_document_upload)
        .sort((a, b) => a.sort_order - b.sort_order)[0] ?? null
  } catch {
    errorMessage.value = 'Impossible de charger les moyens de paiement.'
  } finally {
    loadingMethods.value = false
  }
})

async function startPayment() {
  if (!payzenMethod.value) return
  if (!isAuthenticated.value) {
    errorMessage.value = 'Vous devez être connecté pour payer par carte bancaire.'
    return
  }

  initiating.value = true
  errorMessage.value = null

  try {
    const returnUrl = `${window.location.origin}/paiement/retour`
    const result = await initiatePayment({
      payment_method_id: payzenMethod.value.id,
      amount: String(cartStore.totalAmount),
      currency: 'XPF',
      return_url: returnUrl,
    })

    localStorage.setItem(PENDING_PAYMENT_KEY, result.payment_id)
    formToken.value = result.form_token

    if (result.form_token && result.server_url && result.public_key) {
      await loadPayzenSmartForm({
        serverUrl: result.server_url,
        publicKey: result.public_key,
        token: result.form_token,
        returnUrl,
      })
    } else {
      errorMessage.value = 'Le formulaire de paiement n\'est pas disponible. Veuillez réessayer.'
      formToken.value = null
    }
  } catch (err: unknown) {
    const msg =
      err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : null
    errorMessage.value = msg ?? 'Une erreur est survenue lors de l\'initialisation du paiement.'
  } finally {
    initiating.value = false
  }
}

interface SmartFormOptions {
  serverUrl: string
  publicKey: string
  token: string
  returnUrl: string
}

function loadPayzenSmartForm({ serverUrl, publicKey, token, returnUrl }: SmartFormOptions): Promise<void> {
  return new Promise((resolve, reject) => {
    // Prevent double-loading
    const existing = document.getElementById('kr-payzen-script')
    if (existing) existing.remove()

    const script = document.createElement('script')
    script.id = 'kr-payzen-script'
    script.src = `${serverUrl}/static/js/krypton-client/V4.0/ext/smartform.min.js`
    script.setAttribute('kr-public-key', publicKey)
    script.setAttribute('kr-post-url-success', returnUrl)
    script.setAttribute('kr-language', 'fr-FR')
    script.onload = () => {
      // Inject the SmartForm container with the form token
      const container = document.getElementById('kr-smart-form-container')
      if (container) {
        container.innerHTML = `<div class="kr-smart-form" kr-form-token="${token}"></div>`
      }
      resolve()
    }
    script.onerror = () => reject(new Error('Impossible de charger le script Payzen'))
    document.head.appendChild(script)
  })
}
</script>
