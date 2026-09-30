<template>
  <q-page class="admin-page">
    <PageHeader
      title="Demandes de groupe"
      hint="Demandes de passage à un groupe de prix professionnel, à approuver ou rejeter."
    >
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-toggle v-model="pendingOnly" label="En attente uniquement" @update:model-value="load" />
    </div>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-user_id="props">
        <q-td :props="props"
          ><span class="font-mono" :title="props.row.user_id">{{
            props.row.user_id.slice(0, 8)
          }}</span></q-td
        >
      </template>
      <template #body-cell-price_group_id="props">
        <q-td :props="props">{{ groupLabel(props.row.price_group_id) }}</q-td>
      </template>
      <template #body-cell-business_registration_number="props">
        <q-td :props="props" class="font-mono">{{ props.row.business_registration_number }}</q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            :label="statusLabel(props.row.status)"
            :tone="toneOf(statusColor(props.row.status))"
            :icon="toneIcon(toneOf(statusColor(props.row.status)))"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <template v-if="props.row.status === 'PENDING'">
            <q-btn
              flat
              dense
              no-caps
              icon="ph:check"
              label="Approuver"
              @click="openReview(props.row, 'approve')"
            />
            <q-btn
              flat
              dense
              no-caps
              icon="ph:x"
              color="negative"
              label="Rejeter"
              @click="openReview(props.row, 'reject')"
            />
          </template>
          <span v-else class="text-subtle text-caption">{{ props.row.admin_comment || '—' }}</span>
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{ loading ? 'Chargement…' : 'Aucune demande.' }}</span>
      </template>
    </q-table>

    <q-dialog v-model="reviewDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ action === 'approve' ? 'Approuver la demande' : 'Rejeter la demande' }}
          </h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
          <dl class="admin-dl">
            <dt>Groupe demandé</dt>
            <dd>
              <strong>{{ reviewing ? groupLabel(reviewing.price_group_id) : '' }}</strong>
            </dd>
            <dt>N° d'enregistrement</dt>
            <dd class="font-mono">{{ reviewing?.business_registration_number }}</dd>
          </dl>
          <div v-if="reviewing?.attestation_notes" class="text-caption text-muted">
            « {{ reviewing.attestation_notes }} »
          </div>
          <q-input
            v-model="comment"
            label="Commentaire (optionnel)"
            outlined
            dense
            type="textarea"
            autogrow
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps label="Annuler" v-close-popup />
          <q-btn
            :color="action === 'approve' ? 'primary' : 'negative'"
            unelevated
            no-caps
            :label="action === 'approve' ? 'Approuver' : 'Rejeter'"
            :loading="saving"
            @click="submitReview"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
import {
  approveGroupUpgradeRequest,
  listGroupUpgradeRequests,
  rejectGroupUpgradeRequest,
  type GroupUpgradeRequest,
  type UpgradeRequestStatus,
} from '@/api/groupUpgrades';
import { listPriceGroups, type PriceGroup } from '@/api/eligibility';
import { extractApiError } from '@/api/errors';

const rows = ref<GroupUpgradeRequest[]>([]);
const groups = ref<PriceGroup[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const pendingOnly = ref(true);

const columns: QTableColumn[] = [
  { name: 'created_at', label: 'Demandée', field: 'created_at', align: 'left' },
  { name: 'user_id', label: 'Client', field: 'user_id', align: 'left' },
  { name: 'price_group_id', label: 'Groupe', field: 'price_group_id', align: 'left' },
  {
    name: 'business_registration_number',
    label: 'N° TAHITI',
    field: 'business_registration_number',
    align: 'left',
  },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

function groupLabel(id: string): string {
  return groups.value.find((g) => g.id === id)?.label ?? id.slice(0, 8);
}
function statusLabel(status: UpgradeRequestStatus): string {
  return { PENDING: 'En attente', APPROVED: 'Approuvée', REJECTED: 'Rejetée' }[status];
}
function statusColor(status: UpgradeRequestStatus): string {
  return { PENDING: 'orange', APPROVED: 'green', REJECTED: 'negative' }[status];
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [reqs, grps] = await Promise.all([
      listGroupUpgradeRequests({ pending_only: pendingOnly.value }),
      groups.value.length ? Promise.resolve(groups.value) : listPriceGroups(),
    ]);
    rows.value = reqs;
    groups.value = grps;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

const reviewDialog = ref(false);
const reviewing = ref<GroupUpgradeRequest | null>(null);
const action = ref<'approve' | 'reject'>('approve');
const comment = ref('');
const saving = ref(false);
const dialogError = ref<string | null>(null);

function openReview(req: GroupUpgradeRequest, act: 'approve' | 'reject') {
  dialogError.value = null;
  reviewing.value = req;
  action.value = act;
  comment.value = '';
  reviewDialog.value = true;
}

async function submitReview() {
  if (!reviewing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    if (action.value === 'approve') {
      await approveGroupUpgradeRequest(reviewing.value.id, comment.value || null);
    } else {
      await rejectGroupUpgradeRequest(reviewing.value.id, comment.value || null);
    }
    reviewDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Action impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
