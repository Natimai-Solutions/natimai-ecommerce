<template>
  <q-page class="admin-page">
    <PageHeader title="Taux de change">
      <template #hint>
        Taux de conversion vers la devise de référence : 1 unité de la devise =
        <em>taux</em> unités de la référence. Mettre à jour clôture le taux courant et en ouvre un
        nouveau.
      </template>
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
      <template #body-cell-currency_code="props">
        <q-td :props="props" class="font-mono">{{ props.row.currency_code }}</q-td>
      </template>
      <template #body-cell-rate_to_reference="props">
        <q-td :props="props" class="font-mono">{{ props.row.rate_to_reference }}</q-td>
      </template>
      <template #body-cell-source="props">
        <q-td :props="props">
          <StatusTag
            :label="props.row.source === 'manual' ? 'manuel' : 'auto'"
            :icon="props.row.source === 'manual' ? 'ph:hand' : 'ph:arrows-clockwise'"
          />
        </q-td>
      </template>
      <template #body-cell-valid_until="props">
        <q-td :props="props">
          <StatusTag v-if="!props.row.valid_until" label="Actif" tone="ok" icon="ph:check-circle" />
          <span v-else>{{ props.row.valid_until }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="ph:pencil-simple"
            label="Mettre à jour"
            @click="openEdit(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucun taux de change.</div>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Nouveau taux — {{ editing?.currency_code }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="editForm.rate_to_reference"
              label="Taux vers référence *"
              type="number"
              step="0.000001"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="editForm.valid_from"
              label="Valide à partir du *"
              type="date"
              outlined
              dense
              :rules="req"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { listCurrencyRates, upsertCurrencyRate, type CurrencyRate } from '@/api/currencyRates';
import { extractApiError } from '@/api/errors';

const rows = ref<CurrencyRate[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || 'Requis',
];

const columns: QTableColumn[] = [
  { name: 'currency_code', label: 'Devise', field: 'currency_code', align: 'left' },
  {
    name: 'rate_to_reference',
    label: 'Taux → référence',
    field: 'rate_to_reference',
    align: 'left',
  },
  { name: 'valid_from', label: 'Valide depuis', field: 'valid_from', align: 'left' },
  { name: 'valid_until', label: 'Clôture', field: 'valid_until', align: 'left' },
  { name: 'source', label: 'Source', field: 'source', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listCurrencyRates();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

const editDialog = ref(false);
const editing = ref<CurrencyRate | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editForm = reactive({ rate_to_reference: '', valid_from: '' });

function openEdit(rate: CurrencyRate) {
  dialogError.value = null;
  editing.value = rate;
  editForm.rate_to_reference = rate.rate_to_reference;
  editForm.valid_from = new Date().toISOString().slice(0, 10);
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await upsertCurrencyRate(editing.value.currency_code, {
      rate_to_reference: editForm.rate_to_reference,
      valid_from: editForm.valid_from,
    });
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Mise à jour impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
