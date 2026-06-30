<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Taux de change</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Taux de conversion vers la devise de référence : 1 unité de la devise =
      <em>taux</em> unités de la référence. Mettre à jour clôture le taux courant et en ouvre un
      nouveau.
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
      <template #body-cell-source="props">
        <q-td :props="props">
          <q-chip
            dense
            :color="props.row.source === 'manual' ? 'blue-grey' : 'teal'"
            text-color="white"
            :label="props.row.source === 'manual' ? 'manuel' : 'auto'"
          />
        </q-td>
      </template>
      <template #body-cell-valid_until="props">
        <q-td :props="props">
          <q-chip
            v-if="!props.row.valid_until"
            dense
            color="green"
            text-color="white"
            label="Actif"
          />
          <span v-else>{{ props.row.valid_until }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            icon="edit"
            color="primary"
            label="Mettre à jour"
            no-caps
            @click="openEdit(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">Nouveau taux — {{ editing?.currency_code }}</q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { listCurrencyRates, upsertCurrencyRate, type CurrencyRate } from 'src/api/currencyRates';
import { extractApiError } from 'src/api/errors';

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
