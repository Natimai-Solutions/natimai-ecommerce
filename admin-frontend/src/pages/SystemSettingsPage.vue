<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Paramètres système</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

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
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 380px">
        <q-card-section class="text-h6">{{ editing?.key }}</q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
import {
  listSystemSettings,
  updateSystemSetting,
  type SystemSetting,
} from 'src/api/systemSettings';
import { extractApiError } from 'src/api/errors';

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
