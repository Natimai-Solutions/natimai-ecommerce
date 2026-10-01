<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('specs.title')" :hint="$t('specs.hint')">
      <template #actions>
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('specs.new')"
          @click="openCreate"
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
      <template #body-cell-categories="props">
        <q-td :props="props">
          <q-chip v-for="c in props.row.categories" :key="c" dense :label="c" />
          <span v-if="props.row.categories.length === 0" class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-aliases="props">
        <q-td :props="props">
          <span class="text-muted">{{
            $t('specs.n_aliases', { n: props.row.aliases.length })
          }}</span>
        </q-td>
      </template>
      <template #body-cell-is_active="props">
        <q-td :props="props" align="center">
          <StatusTag
            v-if="props.row.is_active"
            :label="$t('specs.active')"
            tone="ok"
            icon="ph:check-circle"
          />
          <StatusTag v-else :label="$t('specs.inactive')" tone="neutral" icon="ph:minus-circle" />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_active"
            flat
            round
            dense
            icon="ph:trash"
            color="negative"
            @click="confirmDelete(props.row)"
          >
            <q-tooltip>{{ $t('specs.disable') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('specs.none') }}</div>
      </template>
    </q-table>

    <!-- Create / edit dialog -->
    <q-dialog v-model="dialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editingKey ? $t('specs.edit_title', { key: editingKey }) : $t('specs.new_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.key"
              :label="$t('specs.key')"
              outlined
              dense
              :readonly="!!editingKey"
              :rules="req"
            />
            <q-input
              v-model="form.label_fr"
              :label="$t('specs.label_fr')"
              outlined
              dense
              :rules="req"
            />
            <q-select
              v-model="form.type"
              :options="typeOptions"
              :label="$t('specs.type')"
              outlined
              dense
              emit-value
              map-options
              :rules="req"
            />
            <q-input v-model="form.unit" :label="$t('specs.unit')" outlined dense bottom-slots />
            <q-select
              v-model="form.categories"
              :label="$t('specs.categories')"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              bottom-slots
              :options="[]"
            />
            <q-select
              v-model="form.aliases"
              :label="$t('specs.aliases')"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              bottom-slots
              :options="[]"
            />
            <q-toggle v-if="editingKey" v-model="form.is_active" :label="$t('specs.active')" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="editingKey ? $t('specs.save') : $t('specs.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Delete confirm -->
    <q-dialog v-model="deleteDialog">
      <q-card class="app-dialog app-dialog--narrow">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('specs.disable_q') }}</h2>
          <p class="app-dialog__text">
            {{ $t('specs.key_short') }} <span class="font-mono">{{ toDelete?.key }}</span>
          </p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            flat
            no-caps
            :label="$t('specs.disable')"
            color="negative"
            :loading="deleting"
            @click="performDelete"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  createSpecDefinition,
  deleteSpecDefinition,
  listSpecDefinitions,
  updateSpecDefinition,
  type SpecDefinition,
} from '@/api/specDefinitions';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<SpecDefinition[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];
const typeOptions = computed(() => [
  { label: t('specs.numeric'), value: 'numeric' },
  { label: t('specs.enum'), value: 'enum' },
]);

const columns = computed<QTableColumn[]>(() => [
  { name: 'key', label: t('specs.col_key'), field: 'key', align: 'left', classes: 'font-mono' },
  { name: 'label_fr', label: t('specs.col_label'), field: 'label_fr', align: 'left' },
  { name: 'type', label: t('specs.col_type'), field: 'type', align: 'left' },
  { name: 'unit', label: t('specs.col_unit'), field: (r) => r.unit ?? '—', align: 'left' },
  { name: 'categories', label: t('specs.col_categories'), field: 'categories', align: 'left' },
  { name: 'aliases', label: t('specs.col_aliases'), field: 'aliases', align: 'left' },
  { name: 'is_active', label: t('specs.col_status'), field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listSpecDefinitions();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

const dialog = ref(false);
const editingKey = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive({
  key: '',
  label_fr: '',
  type: 'numeric',
  unit: '',
  categories: [] as string[],
  aliases: [] as string[],
  is_active: true,
});

function openCreate() {
  dialogError.value = null;
  editingKey.value = null;
  form.key = '';
  form.label_fr = '';
  form.type = 'numeric';
  form.unit = '';
  form.categories = [];
  form.aliases = [];
  form.is_active = true;
  dialog.value = true;
}

function openEdit(spec: SpecDefinition) {
  dialogError.value = null;
  editingKey.value = spec.key;
  form.key = spec.key;
  form.label_fr = spec.label_fr;
  form.type = spec.type;
  form.unit = spec.unit ?? '';
  form.categories = [...spec.categories];
  form.aliases = [...spec.aliases];
  form.is_active = spec.is_active;
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    if (editingKey.value) {
      await updateSpecDefinition(editingKey.value, {
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        categories: form.categories,
        aliases: form.aliases,
        is_active: form.is_active,
      });
    } else {
      await createSpecDefinition({
        key: form.key,
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        categories: form.categories,
        aliases: form.aliases,
      });
    }
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

const deleteDialog = ref(false);
const deleting = ref(false);
const toDelete = ref<SpecDefinition | null>(null);

function confirmDelete(spec: SpecDefinition) {
  toDelete.value = spec;
  deleteDialog.value = true;
}

async function performDelete() {
  if (!toDelete.value) return;
  deleting.value = true;
  try {
    await deleteSpecDefinition(toDelete.value.key);
    deleteDialog.value = false;
    toDelete.value = null;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('specs.disable_failed');
    deleteDialog.value = false;
  } finally {
    deleting.value = false;
  }
}

onMounted(load);
</script>
