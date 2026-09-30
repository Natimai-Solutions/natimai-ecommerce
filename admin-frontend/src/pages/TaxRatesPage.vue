<template>
  <q-page class="admin-page">
    <PageHeader
      title="Taux TVA / TGC"
      hint="Taux de taxe appliqués par territoire. Un taux est immuable : on le clôture et on en crée un nouveau."
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
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau taux"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-input
        v-model="territory"
        label="Territoire (ex: PF)"
        outlined
        dense
        clearable
        @update:model-value="load"
      />
      <q-select
        v-model="validFilter"
        :options="validOptions"
        label="Validité"
        outlined
        dense
        emit-value
        map-options
        @update:model-value="load"
      />
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
      <template #body-cell-code="props">
        <q-td :props="props" class="font-mono">{{ props.row.code }}</q-td>
      </template>
      <template #body-cell-rate="props">
        <q-td :props="props" class="font-mono">{{ props.row.rate_pct }} %</q-td>
      </template>
      <template #body-cell-valid_until="props">
        <q-td :props="props">
          <StatusTag v-if="!props.row.valid_until" label="Actif" tone="ok" icon="ph:check-circle" />
          <span v-else>{{ props.row.valid_until }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>Modifier (libellé / clôture)</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucun taux.</div>
      </template>
    </q-table>

    <!-- Create dialog -->
    <q-dialog v-model="createDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Nouveau taux</h2>
        </q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.code"
              label="Code (ex: TGC_NORMAL) *"
              outlined
              dense
              :rules="req"
            />
            <q-input v-model="form.label" label="Libellé *" outlined dense :rules="req" />
            <q-input
              v-model="form.rate_pct"
              label="Taux (%) *"
              type="number"
              step="0.01"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.territory_code"
              label="Territoire *"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.valid_from"
              label="Valide à partir du *"
              type="date"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.valid_until"
              label="Valide jusqu'au (optionnel)"
              type="date"
              outlined
              dense
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Créer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Edit dialog (label + valid_until only) -->
    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Modifier {{ editing?.code }}</h2>
          <p class="app-dialog__text">
            Le taux ({{ editing?.rate_pct }} %) est immuable. Pour le changer, créez un nouveau taux
            et clôturez celui-ci.
          </p>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input v-model="editForm.label" label="Libellé" outlined dense />
            <q-input
              v-model="editForm.valid_until"
              label="Clôturer le (valid_until)"
              type="date"
              outlined
              dense
              clearable
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
import { createTaxRate, listTaxRates, updateTaxRate, type TaxRate } from '@/api/taxRates';
import { extractApiError } from '@/api/errors';

const rows = ref<TaxRate[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const territory = ref<string | null>(null);
const validFilter = ref<boolean | null>(null);

const validOptions = [
  { label: 'Tous', value: null },
  { label: 'Actifs', value: true },
  { label: 'Expirés', value: false },
];

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || 'Requis',
];

const columns: QTableColumn[] = [
  { name: 'code', label: 'Code', field: 'code', align: 'left' },
  { name: 'label', label: 'Libellé', field: 'label', align: 'left' },
  { name: 'rate', label: 'Taux', field: 'rate_pct', align: 'left' },
  { name: 'territory_code', label: 'Territoire', field: 'territory_code', align: 'left' },
  { name: 'valid_from', label: 'Valide depuis', field: 'valid_from', align: 'left' },
  { name: 'valid_until', label: 'Clôture', field: 'valid_until', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const params: { territory_code?: string; valid?: boolean } = {};
    if (territory.value) params.territory_code = territory.value;
    if (validFilter.value !== null) params.valid = validFilter.value;
    rows.value = await listTaxRates(params);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// Create
const createDialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive({
  code: '',
  label: '',
  rate_pct: '',
  territory_code: 'PF',
  valid_from: '',
  valid_until: '',
});

function openCreate() {
  dialogError.value = null;
  form.code = '';
  form.label = '';
  form.rate_pct = '';
  form.territory_code = 'PF';
  form.valid_from = new Date().toISOString().slice(0, 10);
  form.valid_until = '';
  createDialog.value = true;
}

async function submitCreate() {
  saving.value = true;
  dialogError.value = null;
  try {
    await createTaxRate({
      code: form.code,
      label: form.label,
      rate_pct: form.rate_pct,
      territory_code: form.territory_code.toUpperCase(),
      valid_from: form.valid_from,
      valid_until: form.valid_until || null,
    });
    createDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Création impossible.';
  } finally {
    saving.value = false;
  }
}

// Edit
const editDialog = ref(false);
const editing = ref<TaxRate | null>(null);
const editForm = reactive<{ label: string; valid_until: string | null }>({
  label: '',
  valid_until: '',
});

function openEdit(rate: TaxRate) {
  dialogError.value = null;
  editing.value = rate;
  editForm.label = rate.label;
  editForm.valid_until = rate.valid_until ?? '';
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await updateTaxRate(editing.value.id, {
      label: editForm.label,
      valid_until: editForm.valid_until || null,
    });
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Modification impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
