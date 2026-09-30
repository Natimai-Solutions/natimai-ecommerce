<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">{{ title }}</h2>
        <p class="app-dialog__text">
          Reste à encaisser :
          <strong class="font-mono">{{ money(remaining) }}</strong
          >. Le paiement est validé dès que les versements atteignent ce montant.
        </p>
      </q-card-section>
      <q-form @submit.prevent="submit">
        <q-card-section class="receipt-form">
          <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
          <div class="receipt-form__row">
            <q-input
              v-model.number="form.amount"
              type="number"
              :step="currencyStep"
              min="0"
              :max="remaining"
              :label="`Montant reçu (${currency})`"
              outlined
              dense
              class="font-mono"
              data-testid="receipt-amount"
              :rules="[
                (v: number) => v > 0 || 'Montant requis',
                (v: number) => v <= remaining || 'Plus que le reste à encaisser',
              ]"
            />
            <q-input
              v-model="form.receivedOn"
              type="date"
              label="Reçu le"
              outlined
              dense
              :max="today"
              data-testid="receipt-date"
            />
          </div>
          <q-select
            v-model="form.method"
            :options="methodOptions"
            label="Mode"
            outlined
            dense
            emit-value
            map-options
            data-testid="receipt-method"
          />
          <q-input
            v-model="form.reference"
            label="Référence (n° de chèque, réf. virement, n° de reçu…)"
            outlined
            dense
            maxlength="100"
          />
          <q-input
            v-model="form.note"
            label="Note (facultative)"
            outlined
            dense
            type="textarea"
            autogrow
            maxlength="500"
          />
          <p class="receipt-form__outcome text-muted">
            <template v-if="form.amount >= remaining && remaining > 0">
              <q-icon name="ph:check-circle" class="text-positive" /> Ce versement solde le
              paiement.
            </template>
            <template v-else-if="form.amount > 0">
              Restera à encaisser :
              <span class="font-mono">{{ money(remaining - form.amount) }}</span>
            </template>
          </p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Annuler" v-close-popup />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="form.amount >= remaining ? 'Encaisser et valider' : 'Enregistrer le versement'"
            :loading="saving"
            :data-testid="confirmTestid"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import { formatMoney } from '@app/utils';
import { extractApiError } from '@/api/errors';
import {
  RECEIPT_METHOD_LABELS,
  recordCounterPayment,
  recordReceipt,
  type ReceiptMethod,
  type ReceiptResult,
} from '@/api/paymentValidations';

/**
 * Enregistre un versement reçu : sur un paiement manuel en attente
 * (`target.paymentId`) ou, au comptoir, sur la part due d'une commande
 * (`target.orderId`, le paiement est créé au besoin).
 */
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    target: { paymentId: string } | { orderId: string } | null;
    remaining: number;
    currency?: string;
    defaultMethod?: ReceiptMethod;
    title?: string;
    confirmTestid?: string;
  }>(),
  {
    currency: 'XPF',
    defaultMethod: 'cash',
    title: 'Encaisser un versement',
    confirmTestid: 'receipt-confirm',
  },
);
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  done: [result: ReceiptResult];
}>();

const today = new Date().toISOString().slice(0, 10);
const form = reactive({
  amount: 0,
  receivedOn: today,
  method: props.defaultMethod,
  reference: '',
  note: '',
});
const saving = ref(false);
const error = ref<string | null>(null);

const counter = computed(() => props.target !== null && 'orderId' in props.target);
const methodOptions = computed(() =>
  (Object.entries(RECEIPT_METHOD_LABELS) as [ReceiptMethod, string][])
    // Au comptoir sans paiement préalable : espèces, chèque ou virement.
    .filter(([value]) => !counter.value || ['cash', 'check', 'transfer'].includes(value))
    .map(([value, label]) => ({ value, label })),
);
const currencyStep = computed(() => (props.currency === 'XPF' ? 1 : 0.01));

function money(value: number): string {
  return formatMoney(value, props.currency);
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    Object.assign(form, {
      amount: props.remaining,
      receivedOn: today,
      method: props.defaultMethod,
      reference: '',
      note: '',
    });
    error.value = null;
  },
);

async function submit() {
  if (!props.target) return;
  saving.value = true;
  error.value = null;
  // Noon local time: the chosen day, whatever the time zone of the server.
  const receivedAt = form.receivedOn === today ? null : `${form.receivedOn}T12:00:00`;
  const input = {
    amount: form.amount,
    received_at: receivedAt,
    method: form.method,
    reference: form.reference.trim() || null,
    note: form.note.trim() || null,
  };
  try {
    const result =
      'paymentId' in props.target
        ? await recordReceipt(props.target.paymentId, input)
        : await recordCounterPayment(props.target.orderId, {
            ...input,
            method: form.method as 'cash' | 'check' | 'transfer',
          });
    emit('done', result);
    emit('update:modelValue', false);
  } catch (err) {
    error.value = extractApiError(err) ?? "Le versement n'a pas pu être enregistré.";
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.receipt-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.receipt-form__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}

.receipt-form__outcome {
  min-height: 20px;
  margin: 4px 0 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
