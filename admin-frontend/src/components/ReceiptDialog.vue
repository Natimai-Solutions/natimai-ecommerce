<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">{{ title || $t('receipt.title') }}</h2>
        <p class="app-dialog__text">
          <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
          <span v-html="$t('receipt.remaining', { amount: money(remaining) })"></span>
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
              :label="$t('receipt.amount', { currency })"
              outlined
              dense
              class="font-mono"
              data-testid="receipt-amount"
              :rules="[
                (v: number) => v > 0 || $t('receipt.amount_rule'),
                (v: number) => v <= remaining || $t('receipt.max_rule'),
              ]"
            />
            <q-input
              v-model="form.receivedOn"
              type="date"
              :label="$t('receipt.received_on')"
              outlined
              dense
              :max="today"
              data-testid="receipt-date"
            />
          </div>
          <q-select
            v-model="form.method"
            :options="methodOptions"
            :label="$t('receipt.mode')"
            outlined
            dense
            emit-value
            map-options
            data-testid="receipt-method"
          />
          <q-input
            v-model="form.reference"
            :label="$t('receipt.reference')"
            outlined
            dense
            maxlength="100"
          />
          <q-input
            v-model="form.note"
            :label="$t('receipt.note')"
            outlined
            dense
            type="textarea"
            autogrow
            maxlength="500"
          />
          <p class="receipt-form__outcome text-muted">
            <template v-if="form.amount >= remaining && remaining > 0">
              <q-icon name="ph:check-circle" class="text-positive" /> {{ $t('receipt.settles') }}
            </template>
            <template v-else-if="form.amount > 0">
              {{ $t('receipt.will_remain') }}
              <span class="font-mono">{{ money(remaining - form.amount) }}</span>
            </template>
          </p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="form.amount >= remaining ? $t('receipt.collect_validate') : $t('receipt.save')"
            :loading="saving"
            :data-testid="confirmTestid"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, reactive, ref, watch } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import { decimalsOf, formatMoney } from '@app/utils';
import { extractApiError } from '@/api/errors';
import {
  RECEIPT_METHOD_LABELS,
  recordCounterPayment,
  recordReceipt,
  type ReceiptMethod,
  type ReceiptResult,
} from '@/api/paymentValidations';

const { t } = useI18n();

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
    title: '',
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
const currencyStep = computed(() => 10 ** -decimalsOf(props.currency));

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
    error.value = extractApiError(err) ?? t('receipt.failed');
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
