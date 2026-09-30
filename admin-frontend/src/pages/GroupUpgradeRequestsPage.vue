<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Demandes d'upgrade de groupe</div>
      <q-toggle v-model="pendingOnly" label="En attente uniquement" @update:model-value="load" />
      <q-btn
        flat
        icon="refresh"
        label="Actualiser"
        class="q-ml-md"
        :loading="loading"
        @click="load"
      />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

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
          ><span :title="props.row.user_id">{{ props.row.user_id.slice(0, 8) }}</span></q-td
        >
      </template>
      <template #body-cell-price_group_id="props">
        <q-td :props="props">{{ groupLabel(props.row.price_group_id) }}</q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            :color="statusColor(props.row.status)"
            text-color="white"
            :label="statusLabel(props.row.status)"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <template v-if="props.row.status === 'PENDING'">
            <q-btn
              flat
              dense
              icon="check"
              color="positive"
              label="Approuver"
              no-caps
              @click="openReview(props.row, 'approve')"
            />
            <q-btn
              flat
              dense
              icon="close"
              color="negative"
              label="Rejeter"
              no-caps
              @click="openReview(props.row, 'reject')"
            />
          </template>
          <span v-else class="text-grey-6 text-caption">{{ props.row.admin_comment || '—' }}</span>
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="reviewDialog">
      <q-card style="min-width: 380px">
        <q-card-section class="text-h6">
          {{ action === 'approve' ? 'Approuver la demande' : 'Rejeter la demande' }}
        </q-card-section>
        <q-card-section class="q-pt-none q-gutter-sm">
          <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
            dialogError
          }}</q-banner>
          <div class="text-body2">
            Groupe demandé :
            <strong>{{ reviewing ? groupLabel(reviewing.price_group_id) : '' }}</strong
            ><br />
            N° d'enregistrement : {{ reviewing?.business_registration_number }}
          </div>
          <div v-if="reviewing?.attestation_notes" class="text-caption text-grey-8">
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
        <q-card-actions align="right">
          <q-btn flat label="Annuler" v-close-popup />
          <q-btn
            :color="action === 'approve' ? 'positive' : 'negative'"
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
