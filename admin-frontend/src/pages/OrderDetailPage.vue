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
              <div class="row items-center q-mb-sm">
                <div class="text-subtitle1 col">Informations</div>
                <q-chip
                  dense
                  :color="orderStatusColor(order.status)"
                  text-color="white"
                  :label="orderStatusLabel(order.status)"
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
                <q-separator class="q-my-xs" />
                <q-item class="q-px-none text-weight-bold">
                  <q-item-section>Total</q-item-section>
                  <q-item-section side>{{ formatMoney(order.total_amount) }}</q-item-section>
                </q-item>
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
                <td class="text-left">{{ providerLabel(p.provider_code) }}</td>
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
  orderStatusColor,
  orderStatusLabel,
  type AdminOrderDetail,
  type AdminOrderPaymentItem,
} from 'src/api/orders';
import { capturePayment, refundPayment } from 'src/api/paymentValidations';
import { extractApiError } from 'src/api/errors';

const route = useRoute();
const orderId = computed(() => String(route.params.id ?? ''));

const order = ref<AdminOrderDetail | null>(null);
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
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
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
