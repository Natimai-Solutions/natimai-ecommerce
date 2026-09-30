<template>
  <q-page class="admin-page">
    <PageHeader title="Paramètres" hint="Réglages techniques de la plateforme, clé par clé.">
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
      row-key="key"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-key="props">
        <q-td :props="props" class="font-mono">{{ props.row.key }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{ loading ? 'Chargement…' : 'Aucun paramètre.' }}</span>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title font-mono">{{ editing?.key }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input v-model="editForm.value" label="Valeur *" outlined dense :rules="req" />
            <q-input
              v-model="editForm.description"
              label="Description"
              outlined
              dense
              type="textarea"
              autogrow
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
import PageHeader from '@/components/PageHeader.vue';
import { listSystemSettings, updateSystemSetting, type SystemSetting } from '@/api/systemSettings';
import { extractApiError } from '@/api/errors';

const rows = ref<SystemSetting[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || 'Requis',
];

const columns: QTableColumn[] = [
  { name: 'key', label: 'Clé', field: 'key', align: 'left' },
  { name: 'value', label: 'Valeur', field: 'value', align: 'left' },
  { name: 'description', label: 'Description', field: (r) => r.description ?? '—', align: 'left' },
  { name: 'updated_at', label: 'Maj', field: 'updated_at', align: 'left' },
  { name: 'actions', label: '', field: 'key', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listSystemSettings();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

const editDialog = ref(false);
const editing = ref<SystemSetting | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editForm = reactive({ value: '', description: '' });

function openEdit(setting: SystemSetting) {
  dialogError.value = null;
  editing.value = setting;
  editForm.value = setting.value;
  editForm.description = setting.description ?? '';
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await updateSystemSetting(editing.value.key, {
      value: editForm.value,
      description: editForm.description || null,
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
