<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <q-btn flat dense round icon="arrow_back" class="q-mr-sm" to="/orders" />
      <div class="text-h6 col">Commande #{{ orderId.slice(0, 8) }}</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner color="primary" size="2em" />
    </div>

    <template v-else-if="order">
      <div class="row q-col-gutter-md">
        <!-- Header / client -->
        <div class="col-12 col-md-6">
          <q-card flat bordered>
            <q-card-section>
              <div class="row items-center q-mb-sm q-gutter-sm">
                <div class="text-subtitle1 col">Informations</div>
                <q-chip
                  dense
                  :color="orderStatusColor(order.status)"
                  text-color="white"
                  :label="orderStatusLabel(order.status)"
                />
                <q-select
                  :model-value="order.status"
                  :options="statusOptions"
                  label="Changer le statut"
                  dense
                  outlined
                  emit-value
                  map-options
                  style="min-width: 230px"
                  :loading="statusSaving"
                  @update:model-value="changeStatus"
                />
              </div>
              <q-list dense>
                <q-item class="q-px-none">
                  <q-item-section>Client</q-item-section>
                  <q-item-section side class="text-right">
                    {{ order.user_name || order.user_email || order.user_id.slice(0, 8) }}
                  </q-item-section>
                </q-item>
                <q-item v-if="order.user_email" class="q-px-none">
                  <q-item-section>Email</q-item-section>
                  <q-item-section side>{{ order.user_email }}</q-item-section>
                </q-item>
                <q-item class="q-px-none">
                  <q-item-section>Date</q-item-section>
                  <q-item-section side>{{ formatDate(order.created_at) }}</q-item-section>
                </q-item>
                <q-item class="q-px-none">
                  <q-item-section>Adresse de livraison</q-item-section>
                  <q-item-section side class="text-right">
                    {{ order.shipping_address || '—' }}
                  </q-item-section>
                </q-item>
                <q-item v-if="order.notes" class="q-px-none">
                  <q-item-section>Notes</q-item-section>
                  <q-item-section side class="text-right">{{ order.notes }}</q-item-section>
                </q-item>
                <q-item class="q-px-none">
                  <q-item-section>Départ groupé</q-item-section>
                  <q-item-section side style="min-width: 260px">
                    <q-select
                      :model-value="order.grouped_departure_id"
                      :options="departureOptions"
                      dense
                      outlined
                      emit-value
                      map-options
                      :loading="departureSaving"
                      @update:model-value="setDeparture"
                    />
                  </q-item-section>
                </q-item>
              </q-list>
            </q-card-section>
          </q-card>
        </div>

        <!-- Amounts -->
        <div class="col-12 col-md-6">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 q-mb-sm">Montants</div>
              <q-list dense>
                <q-item class="q-px-none">
                  <q-item-section>Sous-total</q-item-section>
                  <q-item-section side>{{ formatMoney(order.subtotal_amount) }}</q-item-section>
                </q-item>
                <q-item class="q-px-none">
                  <q-item-section>Frais de port</q-item-section>
                  <q-item-section side>{{ formatMoney(order.shipping_fee_amount) }}</q-item-section>
                </q-item>
                <q-item class="q-px-none">
                  <q-item-section>Frais de paiement</q-item-section>
                  <q-item-section side>{{ formatMoney(order.payment_fee_amount) }}</q-item-section>
                </q-item>
                <q-item v-if="order.deposit_fee_amount > 0" class="q-px-none">
                  <q-item-section>Frais option acompte</q-item-section>
                  <q-item-section side>{{ formatMoney(order.deposit_fee_amount) }}</q-item-section>
                </q-item>
                <q-separator class="q-my-xs" />
                <q-item class="q-px-none text-weight-bold">
                  <q-item-section>Total</q-item-section>
                  <q-item-section side>{{ formatMoney(order.total_amount) }}</q-item-section>
                </q-item>
                <template v-if="order.payment_plan === 'deposit'">
                  <q-item class="q-px-none">
                    <q-item-section>Acompte à la commande</q-item-section>
                    <q-item-section side>{{ formatMoney(order.deposit_amount) }}</q-item-section>
                  </q-item>
                  <q-item class="q-px-none">
                    <q-item-section>
                      Solde
                      <q-item-label caption>
                        <template v-if="order.balance_paid_at">réglé le {{ formatDate(order.balance_paid_at) }}</template>
                        <template v-else-if="order.balance_requested_at">demandé le {{ formatDate(order.balance_requested_at) }}</template>
                        <template v-else>demandé automatiquement à la réception</template>
                      </q-item-label>
                    </q-item-section>
                    <q-item-section side>
                      <div class="row items-center q-gutter-xs">
                        <span>{{ formatMoney(order.balance_amount) }}</span>
                        <q-btn
                          v-if="!order.balance_paid_at"
                          flat
                          dense
                          no-caps
                          size="sm"
                          color="primary"
                          icon="mail"
                          :label="order.balance_requested_at ? 'Renvoyer la demande' : 'Demander le solde'"
                          :loading="requestingBalance"
                          @click="sendBalanceRequest"
                        />
                      </div>
                    </q-item-section>
                  </q-item>
                </template>
              </q-list>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <!-- Lines -->
      <q-card flat bordered class="q-mt-md">
        <q-card-section>
          <div class="text-subtitle1 q-mb-sm">Articles</div>
          <q-markup-table flat dense>
            <thead>
              <tr>
                <th class="text-left">Produit</th>
                <th class="text-right">Qté</th>
                <th class="text-right">PU</th>
                <th class="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in order.lines" :key="line.product_id">
                <td class="text-left">{{ line.product_name || line.product_id.slice(0, 8) }}</td>
                <td class="text-right">{{ line.quantity }}</td>
                <td class="text-right">{{ formatMoney(line.unit_price) }}</td>
                <td class="text-right">{{ formatMoney(line.line_total) }}</td>
              </tr>
              <tr v-if="order.lines.length === 0">
                <td colspan="4" class="text-center text-grey-6">Aucun article.</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>

      <!-- Transport (journey legs, carrier hand-over) -->
      <q-card flat bordered class="q-mt-md">
        <q-card-section>
          <div class="row items-center q-mb-sm">
            <div class="text-subtitle1 col">Transport</div>
            <q-btn
              flat
              dense
              no-caps
              icon="inventory_2"
              label="Page Logistique"
              color="grey-8"
              to="/shipping"
            />
          </div>
          <q-banner v-if="journeyNotice" class="bg-green-1 text-green-9 q-mb-sm" rounded dense>
            {{ journeyNotice }}
          </q-banner>
          <q-banner v-if="journeyError" class="bg-red-1 text-red-9 q-mb-sm" rounded dense>
            {{ journeyError }}
          </q-banner>
          <div v-if="order.delivery_type" class="text-caption text-grey-7 q-mb-sm">
            Mode choisi par le client : {{ prettifyMode(order.delivery_type) }}
          </div>
          <q-markup-table flat dense>
            <thead>
              <tr>
                <th class="text-left">#</th>
                <th class="text-left">Tronçon</th>
                <th class="text-left">Statut</th>
                <th class="text-left">Transporteur</th>
                <th class="text-left">N° de suivi</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="leg in journey"
                :key="leg.tracking_id"
                :class="{ 'bg-blue-1': leg.is_current }"
              >
                <td class="text-left">{{ leg.sequence_order }}</td>
                <td class="text-left">
                  <div>{{ leg.route_name || '—' }}</div>
                  <div class="text-caption text-grey-7">
                    {{ leg.from_place || '?' }} → {{ leg.to_place || '?' }}
                    <span v-if="leg.mode">({{ leg.mode }})</span>
                  </div>
                </td>
                <td class="text-left">
                  <q-chip
                    dense
                    size="sm"
                    :color="leg.is_terminal ? 'green' : leg.is_current ? 'primary' : 'grey-7'"
                    text-color="white"
                    :label="leg.status_name || leg.status_code || '—'"
                  />
                </td>
                <td class="text-left">
                  {{ leg.carrier_name || (leg.tracking_ref ? 'Suivi interne' : '—') }}
                </td>
                <td class="text-left">
                  <a
                    v-if="leg.tracking_url"
                    :href="leg.tracking_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    >{{ leg.tracking_ref }}</a
                  >
                  <span v-else>{{ leg.tracking_ref || '—' }}</span>
                </td>
                <td class="text-right">
                  <q-btn
                    flat
                    dense
                    no-caps
                    icon="local_shipping"
                    color="primary"
                    label="Remettre au transporteur"
                    :disable="leg.is_terminal || leg.status_code === 'shipped'"
                    @click="openShip(leg)"
                  >
                    <q-tooltip max-width="320px">
                      Enregistre le transporteur et le n° de suivi, marque le tronçon expédié et
                      notifie le client.
                    </q-tooltip>
                  </q-btn>
                  <q-btn
                    v-if="!leg.is_final_leg"
                    flat
                    dense
                    no-caps
                    icon="skip_next"
                    color="indigo"
                    label="Tronçon suivant"
                    :disable="leg.is_terminal"
                    @click="advanceLeg(leg)"
                  />
                  <q-btn
                    v-else
                    flat
                    dense
                    no-caps
                    icon="task_alt"
                    color="positive"
                    label="Livrer"
                    :disable="leg.is_terminal"
                    @click="deliverLeg(leg)"
                  />
                </td>
              </tr>
              <tr v-if="journey.length === 0">
                <td colspan="6" class="text-center text-grey-6">
                  {{ journeyLoading ? 'Chargement…' : 'Aucun tronçon de transport.' }}
                </td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>

      <!-- Ship dialog (carrier + tracking ref) -->
      <q-dialog v-model="shipDialog">
        <q-card style="min-width: 360px">
          <q-card-section class="text-h6">Remise au transporteur</q-card-section>
          <q-form @submit.prevent="submitShip">
            <q-card-section class="q-pt-none q-gutter-sm">
              <q-banner v-if="shipError" class="bg-red-1 text-red-9" dense rounded>{{
                shipError
              }}</q-banner>
              <q-select
                v-model="shipCarrierId"
                :options="carrierOptions"
                label="Transporteur"
                outlined
                dense
                emit-value
                map-options
              />
              <q-input
                v-model="shipRef"
                label="Numéro de suivi (optionnel)"
                hint="Laisser vide si vous n'avez pas de numéro (suivi géré en interne)."
                outlined
                dense
                autofocus
              />
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat label="Annuler" v-close-popup />
              <q-btn
                type="submit"
                color="primary"
                label="Remettre au transporteur"
                :loading="shipping"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>

      <!-- Payments -->
      <q-card flat bordered class="q-mt-md">
        <q-card-section>
          <div class="text-subtitle1 q-mb-sm">Paiements</div>
          <q-banner v-if="refundNotice" class="bg-green-1 text-green-9 q-mb-sm" rounded dense>
            {{ refundNotice }}
          </q-banner>
          <q-markup-table flat dense>
            <thead>
              <tr>
                <th class="text-left">Type</th>
                <th class="text-left">Référence</th>
                <th class="text-left">Statut</th>
                <th class="text-right">Montant</th>
                <th class="text-left">Date</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in order.payments" :key="p.payment_id">
                <td class="text-left">
                  {{ providerLabel(p.provider_code) }}
                  <q-badge v-if="p.kind !== 'full'" color="teal" class="q-ml-xs" :label="PAYMENT_KIND_LABELS[p.kind] ?? p.kind" />
                </td>
                <td class="text-left">{{ p.provider_reference || '—' }}</td>
                <td class="text-left">{{ p.status || '—' }}</td>
                <td class="text-right">{{ formatMoney(p.amount) }}</td>
                <td class="text-left">{{ formatDate(p.created_at) }}</td>
                <td class="text-right">
                  <q-btn
                    v-if="canCapture(p)"
                    flat
                    dense
                    no-caps
                    color="primary"
                    icon="payments"
                    label="Capturer"
                    :loading="capturingId === p.payment_id"
                    @click="captureRow(p)"
                  />
                  <q-btn
                    v-if="canRefund(p)"
                    flat
                    dense
                    no-caps
                    color="negative"
                    icon="undo"
                    label="Rembourser"
                    @click="openRefund(p)"
                  />
                </td>
              </tr>
              <tr v-if="order.payments.length === 0">
                <td colspan="6" class="text-center text-grey-6">Aucun paiement.</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>

      <!-- Refund dialog -->
      <q-dialog v-model="refundDialog">
        <q-card style="min-width: 380px">
          <q-card-section class="text-h6">Rembourser le paiement</q-card-section>
          <q-form @submit.prevent="submitRefund">
            <q-card-section class="q-pt-none q-gutter-sm">
              <q-banner v-if="refundError" class="bg-red-1 text-red-9" dense rounded>{{
                refundError
              }}</q-banner>
              <div class="text-caption text-grey-7">
                Montant du paiement :
                {{ refundTarget ? formatMoney(refundTarget.amount) : '' }}. Laissez le montant vide
                pour un remboursement total.
              </div>
              <q-input
                v-model.number="refundAmount"
                label="Montant à rembourser (optionnel)"
                type="number"
                step="0.01"
                outlined
                dense
                clearable
              />
              <q-input
                v-model="refundReason"
                label="Motif (optionnel)"
                type="textarea"
                autogrow
                outlined
                dense
              />
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat label="Annuler" v-close-popup />
              <q-btn type="submit" color="negative" label="Rembourser" :loading="refunding" />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { formatXpf } from '@app/utils';
import {
  getOrder,
  listOrderStatuses,
  orderStatusColor,
  orderStatusLabel,
  PAYMENT_KIND_LABELS,
  requestBalance,
  setOrderStatus,
  type AdminOrderDetail,
  type AdminOrderPaymentItem,
} from 'src/api/orders';

// --- Deposit order: ask for (or re-send) the balance ---
const requestingBalance = ref(false);
async function sendBalanceRequest() {
  if (!order.value) return;
  requestingBalance.value = true;
  error.value = null;
  try {
    const result = await requestBalance(order.value.order_id);
    order.value.balance_requested_at = new Date().toISOString();
    refundNotice.value = result.sent
      ? `Demande de solde (${formatMoney(result.balance_amount)}) envoyée au client.`
      : "Demande enregistrée, mais l'e-mail n'a pas pu partir (notifications désactivées ?).";
  } catch (err) {
    error.value = extractApiError(err) ?? 'Demande de solde impossible.';
  } finally {
    requestingBalance.value = false;
  }
}
import { capturePayment, refundPayment } from 'src/api/paymentValidations';
import {
  advanceTracking,
  deliverTracking,
  getOrderJourney,
  listCarriers,
  shipTracking,
  type Carrier,
  type JourneyLeg,
} from 'src/api/shipping';
import { extractApiError } from 'src/api/errors';
import { assignOrders, listDepartures, type Departure } from 'src/api/departures';

// --- Order status (one order by hand; the departure handles the bulk case) ---
const statusNames = ref<string[]>([]);
const statusSaving = ref(false);
const statusOptions = computed(() =>
  statusNames.value.map((s) => ({ label: orderStatusLabel(s), value: s })),
);

async function changeStatus(status: string) {
  if (!order.value || status === order.value.status) return;
  statusSaving.value = true;
  error.value = null;
  try {
    await setOrderStatus(order.value.order_id, status);
    order.value.status = status;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Changement de statut impossible.';
  } finally {
    statusSaving.value = false;
  }
}

const route = useRoute();
const orderId = computed(() => String(route.params.id ?? ''));

const order = ref<AdminOrderDetail | null>(null);

// --- Grouped departure (attach / move / detach from the order itself) ---
const departures = ref<Departure[]>([]);
const departureSaving = ref(false);
const departureOptions = computed(() => [
  { label: '— Aucun (commande classique)', value: null },
  ...departures.value.map((d) => ({
    label: `${d.name} (${formatDate(d.order_cutoff_at)})`,
    value: d.id,
  })),
]);

async function setDeparture(departureId: string | null) {
  if (!order.value) return;
  departureSaving.value = true;
  error.value = null;
  try {
    await assignOrders([order.value.order_id], departureId);
    order.value.grouped_departure_id = departureId;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Rattachement impossible.';
  } finally {
    departureSaving.value = false;
  }
}
const loading = ref(false);
const error = ref<string | null>(null);

function formatMoney(amount: number): string {
  return Number.isFinite(amount) ? formatXpf(amount) : String(amount);
}

function formatDate(raw: string | null): string {
  if (!raw) return '—';
  const d = new Date(raw);
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleString('fr-FR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
}

function providerLabel(code: string | null): string {
  if (!code) return '—';
  if (code.startsWith('document') || code.startsWith('po_')) return 'Bon de commande';
  if (code.includes('check') || code.includes('cheque')) return 'Chèque';
  if (code.includes('transfer') || code.includes('virement')) return 'Virement';
  if (code === 'payzen') return 'Carte bancaire';
  if (code.startsWith('manual')) return 'Paiement manuel';
  return code;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    order.value = await getOrder(orderId.value);
    departures.value = await listDepartures().catch(() => []);
    statusNames.value = await listOrderStatuses().catch(() => []);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
  await loadJourney();
}

// --- Transport (journey legs) ---
const journey = ref<JourneyLeg[]>([]);
const journeyLoading = ref(false);
const journeyError = ref<string | null>(null);
const journeyNotice = ref<string | null>(null);
const carriers = ref<Carrier[]>([]);

function prettifyMode(mode: string): string {
  return mode.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

async function loadJourney() {
  journeyLoading.value = true;
  journeyError.value = null;
  try {
    journey.value = await getOrderJourney(orderId.value);
  } catch (err) {
    // 404 = no tracked leg yet (e.g. an order placed before the logistics
    // phase): an empty table, not an error banner.
    journey.value = [];
    const msg = extractApiError(err);
    if (msg && !/aucun tronçon/i.test(msg)) journeyError.value = msg;
  } finally {
    journeyLoading.value = false;
  }
}

const shipDialog = ref(false);
const shipTarget = ref<JourneyLeg | null>(null);
const shipRef = ref('');
const shipCarrierId = ref<string | null>(null);
const shipping = ref(false);
const shipError = ref<string | null>(null);

const carrierOptions = computed<{ label: string; value: string | null }[]>(() => [
  { label: '— Suivi interne (sans transporteur) —', value: null },
  ...carriers.value.map((c) => ({ label: c.name, value: c.id })),
]);

async function openShip(leg: JourneyLeg) {
  shipTarget.value = leg;
  shipRef.value = leg.tracking_ref ?? '';
  shipCarrierId.value = leg.carrier_id;
  shipError.value = null;
  shipDialog.value = true;
  if (carriers.value.length === 0) {
    try {
      carriers.value = await listCarriers();
    } catch {
      // The selector still offers « suivi interne ».
    }
  }
}

async function submitShip() {
  if (!shipTarget.value) return;
  shipping.value = true;
  shipError.value = null;
  try {
    await shipTracking(
      shipTarget.value.tracking_id,
      shipRef.value.trim() || null,
      shipCarrierId.value,
    );
    shipDialog.value = false;
    journeyNotice.value = 'Remise au transporteur enregistrée (client notifié).';
    await loadJourney();
  } catch (err) {
    shipError.value = extractApiError(err) ?? 'Expédition impossible.';
  } finally {
    shipping.value = false;
  }
}

async function advanceLeg(leg: JourneyLeg) {
  journeyError.value = null;
  try {
    const result = await advanceTracking(leg.tracking_id);
    journeyNotice.value = result.message;
    await loadJourney();
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Progression impossible.';
  }
}

async function deliverLeg(leg: JourneyLeg) {
  journeyError.value = null;
  try {
    await deliverTracking(leg.tracking_id);
    journeyNotice.value = 'Colis marqué livré (client notifié).';
    await loadJourney();
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Livraison impossible.';
  }
}

// --- Refund ---
const refundDialog = ref(false);
const refundTarget = ref<AdminOrderPaymentItem | null>(null);
const refundAmount = ref<number | null>(null);
const refundReason = ref('');
const refunding = ref(false);
const refundError = ref<string | null>(null);
const refundNotice = ref<string | null>(null);

/**
 * Show the refund button only when the backend says so: the provider supports
 * an in-app refund (card / PayZen) and the payment is in a refundable state.
 * Manual / document payments are refunded out-of-band, so no button is shown.
 */
function canRefund(p: AdminOrderPaymentItem): boolean {
  return p.can_refund === true;
}

function openRefund(p: AdminOrderPaymentItem) {
  refundTarget.value = p;
  refundAmount.value = null;
  refundReason.value = '';
  refundError.value = null;
  refundDialog.value = true;
}

async function submitRefund() {
  if (!refundTarget.value) return;
  refunding.value = true;
  refundError.value = null;
  try {
    const amount =
      typeof refundAmount.value === 'number' && !Number.isNaN(refundAmount.value)
        ? refundAmount.value
        : null;
    const result = await refundPayment(refundTarget.value.payment_id, {
      amount,
      reason: refundReason.value.trim() || null,
    });
    refundDialog.value = false;
    refundNotice.value =
      result.message ??
      (result.fully_refunded ? 'Remboursement total effectué.' : 'Remboursement effectué.');
    await load();
  } catch (err) {
    refundError.value = extractApiError(err) ?? 'Remboursement impossible.';
  } finally {
    refunding.value = false;
  }
}

// --- Capture (deferred CB debit) ---
const capturingId = ref<string | null>(null);

/** Only authorised (not-yet-debited) card payments can be captured. */
function canCapture(p: AdminOrderPaymentItem): boolean {
  return p.status === 'Authorized';
}

async function captureRow(p: AdminOrderPaymentItem) {
  capturingId.value = p.payment_id;
  error.value = null;
  try {
    const result = await capturePayment(p.payment_id);
    refundNotice.value = result.message ?? 'Paiement capturé.';
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Capture impossible.';
  } finally {
    capturingId.value = null;
  }
}

onMounted(load);
</script>
