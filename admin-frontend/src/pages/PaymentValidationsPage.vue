<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Validation des paiements</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Paiements manuels (chèque / virement) et bons de commande en attente de validation.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{ notice }}</q-banner>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner color="primary" size="2em" />
    </div>

    <q-banner v-else-if="rows.length === 0" class="bg-blue-1 text-blue-10" rounded>
      <template #avatar><q-icon name="info" /></template>
      Aucun paiement en attente de validation.
    </q-banner>

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
          <div class="text-caption text-grey-6">{{ props.row.provider_code }}</div>
        </q-td>
      </template>
      <template #body-cell-amount="props">
        <q-td :props="props" class="text-weight-medium">
          {{ formatMoney(props.row.amount) }}
        </q-td>
      </template>
      <template #body-cell-user_id="props">
        <q-td :props="props">
          <div :title="props.row.user_id">
            {{ props.row.user_name || props.row.user_email || props.row.user_id.slice(0, 8) }}
          </div>
          <div
            v-if="props.row.user_name && props.row.user_email"
            class="text-caption text-grey-6"
          >
            {{ props.row.user_email }}
          </div>
        </q-td>
      </template>
      <template #body-cell-order_id="props">
        <q-td :props="props">
          <q-btn
            v-if="props.row.order_id"
            flat
            dense
            no-caps
            color="primary"
            :label="`#${props.row.order_id.slice(0, 8)}`"
            :to="`/orders/${props.row.order_id}`"
            :title="props.row.order_id"
          />
          <span v-else class="text-grey-5">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="props.row.is_document"
            flat
            dense
            icon="description"
            color="primary"
            label="Pièces"
            no-caps
            @click="openAttachments(props.row)"
          />
          <q-btn flat dense icon="check" color="positive" label="Approuver" no-caps @click="openApprove(props.row)" />
          <q-btn flat dense icon="close" color="negative" label="Rejeter" no-caps @click="openReject(props.row)" />
        </q-td>
      </template>
    </q-table>

    <!-- Approve -->
    <q-dialog v-model="approveDialog">
      <q-card style="min-width: 380px">
        <q-card-section class="text-h6">Approuver le paiement</q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{ dialogError }}</q-banner>
          <div class="text-body2">
            {{ providerLabel(current?.provider_code ?? '') }} —
            <strong>{{ current ? formatMoney(current.amount) : '' }}</strong>
          </div>
          <q-input
            v-if="!current?.is_document"
            v-model="approveForm.reference"
            label="Référence (n° de chèque, réf. virement…)"
            outlined
            dense
          />
          <div v-else class="text-caption text-grey-7">
            Bon de commande : aucune référence de transaction n'est requise — vérifiez la pièce
            jointe puis approuvez.
          </div>
          <q-input v-model="approveForm.comment" label="Commentaire (optionnel)" outlined dense type="textarea" autogrow />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Annuler" v-close-popup />
          <q-btn color="positive" label="Approuver" :loading="saving" @click="submitApprove" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Reject -->
    <q-dialog v-model="rejectDialog">
      <q-card style="min-width: 380px">
        <q-card-section class="text-h6">Rejeter le paiement</q-card-section>
        <q-form @submit.prevent="submitReject">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{ dialogError }}</q-banner>
            <q-input
              v-model="rejectReason"
              label="Motif du rejet *"
              outlined
              dense
              type="textarea"
              autogrow
              :rules="[(v) => (!!v && v.trim().length > 0) || 'Motif requis']"
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="negative" label="Rejeter" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Attachments (BC documents) -->
    <q-dialog v-model="attachmentsDialog">
      <q-card style="min-width: 420px; max-width: 560px">
        <q-card-section class="text-h6">Bon(s) de commande</q-card-section>
        <q-card-section class="q-pt-none">
          <q-banner v-if="dialogError" class="bg-red-1 text-red-9 q-mb-sm" dense rounded>{{ dialogError }}</q-banner>
          <div v-if="loadingAttachments" class="text-center q-pa-md">
            <q-spinner color="primary" size="1.5em" />
          </div>
          <div v-else-if="attachments.length === 0" class="text-grey-6 text-body2">
            Aucune pièce jointe pour ce paiement.
          </div>
          <q-list v-else separator>
            <q-item v-for="att in attachments" :key="att.id">
              <q-item-section avatar><q-icon name="description" color="primary" /></q-item-section>
              <q-item-section>
                <q-item-label>{{ att.filename }}</q-item-label>
                <q-item-label caption>{{ att.mimetype }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-chip dense :color="avColor(att)" text-color="white" :label="avLabel(att)" />
              </q-item-section>
              <q-item-section side>
                <q-btn
                  flat
                  dense
                  icon="download"
                  color="primary"
                  :loading="downloadingId === att.id"
                  :disable="att.av_scanned && att.av_clean === false"
                  @click="download(att)"
                >
                  <q-tooltip>Télécharger</q-tooltip>
                </q-btn>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Fermer" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { formatXpf } from '@app/utils'
import {
  approvePayment,
  getAttachmentDownloadUrl,
  listPaymentAttachments,
  listPendingValidation,
  rejectPayment,
  type PaymentAttachment,
  type PendingPayment,
} from 'src/api/paymentValidations'
import { extractApiError } from 'src/api/errors'

const rows = ref<PendingPayment[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const columns: QTableColumn[] = [
  { name: 'provider', label: 'Type', field: 'provider_code', align: 'left' },
  { name: 'amount', label: 'Montant', field: 'amount', align: 'left' },
  { name: 'reference', label: 'Référence', field: (r) => r.provider_reference ?? '—', align: 'left' },
  { name: 'user_id', label: 'Client', field: 'user_id', align: 'left' },
  { name: 'order_id', label: 'Commande', field: 'order_id', align: 'left' },
  { name: 'actions', label: '', field: 'payment_id', align: 'right' },
]

function formatMoney(amount: number): string {
  return Number.isFinite(amount) ? formatXpf(amount) : String(amount)
}

function providerLabel(code: string): string {
  if (code.startsWith('document') || code.startsWith('po_')) return 'Bon de commande'
  if (code.includes('check') || code.includes('cheque')) return 'Chèque'
  if (code.includes('transfer') || code.includes('virement')) return 'Virement'
  if (code.startsWith('manual')) return 'Paiement manuel'
  return code
}

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await listPendingValidation()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

// --- Approve / Reject ---
const current = ref<PendingPayment | null>(null)
const saving = ref(false)
const dialogError = ref<string | null>(null)

const approveDialog = ref(false)
const approveForm = reactive({ reference: '', comment: '' })

function openApprove(p: PendingPayment) {
  dialogError.value = null
  current.value = p
  approveForm.reference = ''
  approveForm.comment = ''
  approveDialog.value = true
}

async function submitApprove() {
  if (!current.value) return
  saving.value = true
  dialogError.value = null
  try {
    await approvePayment(current.value.payment_id, {
      reference: approveForm.reference || null,
      comment: approveForm.comment || null,
    })
    approveDialog.value = false
    notice.value = 'Paiement approuvé.'
    await load()
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Approbation impossible.'
  } finally {
    saving.value = false
  }
}

const rejectDialog = ref(false)
const rejectReason = ref('')

function openReject(p: PendingPayment) {
  dialogError.value = null
  current.value = p
  rejectReason.value = ''
  rejectDialog.value = true
}

async function submitReject() {
  if (!current.value || !rejectReason.value.trim()) return
  saving.value = true
  dialogError.value = null
  try {
    await rejectPayment(current.value.payment_id, rejectReason.value.trim())
    rejectDialog.value = false
    notice.value = 'Paiement rejeté.'
    await load()
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Rejet impossible.'
  } finally {
    saving.value = false
  }
}

// --- Attachments (BC) ---
const attachmentsDialog = ref(false)
const attachments = ref<PaymentAttachment[]>([])
const loadingAttachments = ref(false)
const downloadingId = ref<string | null>(null)

async function openAttachments(p: PendingPayment) {
  dialogError.value = null
  current.value = p
  attachments.value = []
  attachmentsDialog.value = true
  loadingAttachments.value = true
  try {
    attachments.value = await listPaymentAttachments(p.payment_id)
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Chargement des pièces impossible.'
  } finally {
    loadingAttachments.value = false
  }
}

async function download(att: PaymentAttachment) {
  if (!current.value) return
  downloadingId.value = att.id
  dialogError.value = null
  try {
    const url = await getAttachmentDownloadUrl(current.value.payment_id, att.id)
    window.open(url, '_blank', 'noopener')
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Téléchargement impossible.'
  } finally {
    downloadingId.value = null
  }
}

function avLabel(att: PaymentAttachment): string {
  if (!att.av_scanned) return 'analyse…'
  if (att.av_clean) return 'sain'
  return 'infecté'
}
function avColor(att: PaymentAttachment): string {
  if (!att.av_scanned) return 'orange'
  if (att.av_clean) return 'green'
  return 'negative'
}

onMounted(load)
</script>
