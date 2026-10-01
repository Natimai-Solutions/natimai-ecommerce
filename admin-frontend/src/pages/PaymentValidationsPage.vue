<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('payments.title')" :hint="$t('payments.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <div v-else-if="rows.length === 0" class="app-empty">
      <q-icon name="ph:check-circle" size="28px" class="text-subtle" />
      <h3>{{ $t('payments.none') }}</h3>
      <p>
        {{ $t('payments.none_hint') }}
      </p>
    </div>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      row-key="payment_id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-provider="props">
        <q-td :props="props">
          <div>{{ providerLabel(props.row.provider_code) }}</div>
          <div class="text-caption text-subtle font-mono">{{ props.row.provider_code }}</div>
        </q-td>
      </template>
      <template #body-cell-amount="props">
        <q-td :props="props">
          <div class="font-mono text-weight-medium">
            {{ formatMoney(props.row.amount, props.row.currency) }}
          </div>
          <div
            v-if="(props.row.received_amount ?? 0) > 0"
            class="text-caption text-warning"
            data-testid="payment-received"
          >
            {{ $t('payments.received') }}
            <span class="font-mono">{{
              formatMoney(props.row.received_amount, props.row.currency)
            }}</span>
          </div>
        </q-td>
      </template>
      <template #body-cell-reference="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-user_id="props">
        <q-td :props="props">
          <div :title="props.row.user_id">
            {{ props.row.user_name || props.row.user_email || props.row.user_id.slice(0, 8) }}
          </div>
          <div v-if="props.row.user_name && props.row.user_email" class="text-caption text-subtle">
            {{ props.row.user_email }}
          </div>
        </q-td>
      </template>
      <template #body-cell-order_id="props">
        <q-td :props="props">
          <router-link
            v-if="props.row.order_id"
            :to="`/orders/${props.row.order_id}`"
            class="admin-link font-mono"
            :title="props.row.order_id"
            data-testid="payment-order"
            >{{ props.row.order_number ?? `#${props.row.order_id.slice(0, 8)}` }}</router-link
          >
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="props.row.is_document"
            flat
            dense
            no-caps
            icon="ph:file-text"
            :label="$t('payments.documents')"
            @click="openAttachments(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="ph:check"
            color="positive"
            :label="props.row.is_document ? $t('payments.approve') : $t('payments.collect')"
            data-testid="payment-approve"
            @click="props.row.is_document ? openApprove(props.row) : openReceipt(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="ph:x"
            color="negative"
            :label="$t('payments.reject')"
            @click="openReject(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Encaisser un paiement manuel (en une ou plusieurs fois) -->
    <ReceiptDialog
      v-model="receiptDialog"
      :target="current ? { paymentId: current.payment_id } : null"
      :remaining="current ? current.amount - (current.received_amount ?? 0) : 0"
      :currency="current?.currency ?? shopConfig.currency"
      :default-method="defaultReceiptMethod(current?.provider_code)"
      :title="
        $t('payments.collect_title', { provider: providerLabel(current?.provider_code ?? '') })
      "
      confirm-testid="payment-approve-confirm"
      @done="onReceipt"
    />

    <!-- Approve (bon de commande) -->
    <q-dialog v-model="approveDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('payments.approve_title') }}</h2>
          <p class="app-dialog__text">
            {{ providerLabel(current?.provider_code ?? '') }} —
            <strong class="font-mono">{{
              current ? formatMoney(current.amount, current.currency) : ''
            }}</strong>
          </p>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
          <q-input
            v-if="!current?.is_document"
            v-model="approveForm.reference"
            :label="$t('payments.reference')"
            outlined
            dense
          />
          <p v-else class="admin-hint q-mb-none">
            {{ $t('payments.po_hint') }}
          </p>
          <q-input
            v-model="approveForm.comment"
            :label="$t('payments.comment')"
            outlined
            dense
            type="textarea"
            autogrow
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :label="$t('payments.approve')"
            :loading="saving"
            data-testid="payment-approve-confirm"
            @click="submitApprove"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Reject -->
    <q-dialog v-model="rejectDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('payments.reject_title') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitReject">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="rejectReason"
              :label="$t('payments.reason')"
              outlined
              dense
              type="textarea"
              autogrow
              :rules="[(v) => (!!v && v.trim().length > 0) || $t('payments.reason_rule')]"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="negative"
              unelevated
              no-caps
              :label="$t('payments.reject')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Attachments (BC documents) -->
    <q-dialog v-model="attachmentsDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('payments.po_title') }}</h2>
        </q-card-section>
        <q-card-section>
          <AppNotice v-if="dialogError" tone="error" dense class="q-mb-sm">{{
            dialogError
          }}</AppNotice>
          <div v-if="loadingAttachments" class="text-center q-pa-md">
            <q-spinner size="1.5em" />
          </div>
          <div v-else-if="attachments.length === 0" class="text-subtle text-body2">
            {{ $t('payments.no_attachment') }}
          </div>
          <q-list v-else separator>
            <q-item v-for="att in attachments" :key="att.id">
              <q-item-section avatar><q-icon name="ph:file-text" /></q-item-section>
              <q-item-section>
                <q-item-label>{{ att.filename }}</q-item-label>
                <q-item-label caption>{{ att.mimetype }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <StatusTag
                  :label="avLabel(att)"
                  :tone="toneOf(avColor(att))"
                  :icon="toneIcon(toneOf(avColor(att)))"
                />
              </q-item-section>
              <q-item-section side>
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:download-simple"
                  :loading="downloadingId === att.id"
                  :disable="att.av_scanned && att.av_clean === false"
                  @click="download(att)"
                >
                  <q-tooltip>{{ $t('payments.download') }}</q-tooltip>
                </q-btn>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import ReceiptDialog from '@/components/ReceiptDialog.vue';
import { providerLabel } from '@/utils/payments';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import { formatMoney as money } from '@app/utils';
import { useShopConfigStore } from '@/stores/shopConfig';
import PageHeader from '@/components/PageHeader.vue';
import {
  approvePayment,
  type ReceiptMethod,
  type ReceiptResult,
  getAttachmentDownloadUrl,
  listPaymentAttachments,
  listPendingValidation,
  rejectPayment,
  type PaymentAttachment,
  type PendingPayment,
} from '@/api/paymentValidations';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<PendingPayment[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const columns = computed<QTableColumn[]>(() => [
  { name: 'provider', label: t('payments.col_type'), field: 'provider_code', align: 'left' },
  { name: 'amount', label: t('payments.col_amount'), field: 'amount', align: 'right' },
  {
    name: 'reference',
    label: t('payments.col_reference'),
    field: (r) => r.provider_reference ?? '—',
    align: 'left',
  },
  { name: 'user_id', label: t('payments.col_customer'), field: 'user_id', align: 'left' },
  { name: 'order_id', label: t('payments.col_order'), field: 'order_id', align: 'left' },
  { name: 'actions', label: '', field: 'payment_id', align: 'right' },
]);

const shopConfig = useShopConfigStore();

/** Amount in its own currency (the order's), else the reference currency. */
function formatMoney(amount: number, currency?: string | null): string {
  return Number.isFinite(amount) ? money(amount, currency || shopConfig.currency) : String(amount);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listPendingValidation();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// --- Approve / Reject ---
const current = ref<PendingPayment | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);

const approveDialog = ref(false);
const approveForm = reactive({ reference: '', comment: '' });

function openApprove(p: PendingPayment) {
  dialogError.value = null;
  current.value = p;
  approveForm.reference = '';
  approveForm.comment = '';
  approveDialog.value = true;
}

// --- Encaisser (paiements manuels) ---
const receiptDialog = ref(false);

function openReceipt(p: PendingPayment) {
  current.value = p;
  receiptDialog.value = true;
}

function defaultReceiptMethod(code: string | undefined): ReceiptMethod {
  if (code === 'manual_check') return 'check';
  if (code === 'manual_transfer') return 'transfer';
  return 'cash';
}

async function onReceipt(result: ReceiptResult) {
  notice.value = result.payment_settled
    ? t('payments.collected')
    : t('payments.partial', { amount: formatMoney(Number(result.remaining_amount)) });
  await load();
}

async function submitApprove() {
  if (!current.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await approvePayment(current.value.payment_id, {
      reference: approveForm.reference || null,
      comment: approveForm.comment || null,
    });
    approveDialog.value = false;
    notice.value = t('payments.approved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('payments.approve_failed');
  } finally {
    saving.value = false;
  }
}

const rejectDialog = ref(false);
const rejectReason = ref('');

function openReject(p: PendingPayment) {
  dialogError.value = null;
  current.value = p;
  rejectReason.value = '';
  rejectDialog.value = true;
}

async function submitReject() {
  if (!current.value || !rejectReason.value.trim()) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await rejectPayment(current.value.payment_id, rejectReason.value.trim());
    rejectDialog.value = false;
    notice.value = t('payments.rejected');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('payments.reject_failed');
  } finally {
    saving.value = false;
  }
}

// --- Attachments (BC) ---
const attachmentsDialog = ref(false);
const attachments = ref<PaymentAttachment[]>([]);
const loadingAttachments = ref(false);
const downloadingId = ref<string | null>(null);

async function openAttachments(p: PendingPayment) {
  dialogError.value = null;
  current.value = p;
  attachments.value = [];
  attachmentsDialog.value = true;
  loadingAttachments.value = true;
  try {
    attachments.value = await listPaymentAttachments(p.payment_id);
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('payments.docs_failed');
  } finally {
    loadingAttachments.value = false;
  }
}

async function download(att: PaymentAttachment) {
  if (!current.value) return;
  downloadingId.value = att.id;
  dialogError.value = null;
  try {
    const url = await getAttachmentDownloadUrl(current.value.payment_id, att.id);
    window.open(url, '_blank', 'noopener');
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('payments.download_failed');
  } finally {
    downloadingId.value = null;
  }
}

function avLabel(att: PaymentAttachment): string {
  if (!att.av_scanned) return t('payments.av_scanning');
  if (att.av_clean) return t('payments.av_clean');
  return t('payments.av_infected');
}
function avColor(att: PaymentAttachment): string {
  if (!att.av_scanned) return 'orange';
  if (att.av_clean) return 'green';
  return 'negative';
}

onMounted(load);
</script>
