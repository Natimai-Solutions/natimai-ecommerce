<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('carriers.title')">
      <template #actions>
        <q-toggle v-model="showRetired" :label="$t('carriers.show_retired')" />
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('carriers.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <p class="admin-hint">
      <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
      <span v-html="$t('carriers.intro')"></span>
    </p>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

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
      <template #body-cell-template="props">
        <q-td :props="props">
          <span v-if="props.row.tracking_url_template" class="text-caption font-mono">{{
            props.row.tracking_url_template
          }}</span>
          <span v-else class="text-subtle">{{ $t('carriers.no_link') }}</span>
        </q-td>
      </template>
      <template #body-cell-active="props">
        <q-td :props="props">
          <StatusTag
            v-if="props.row.is_active"
            tone="ok"
            icon="ph:check-circle"
            :label="$t('common.active')"
          />
          <StatusTag v-else tone="neutral" icon="ph:minus-circle" :label="$t('carriers.retired')" />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            :aria-label="$t('common.edit')"
            flat
            round
            dense
            icon="ph:pencil-simple"
            @click="openEdit(props.row)"
          >
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('carriers.retire')"
            v-if="props.row.is_active"
            flat
            round
            dense
            icon="ph:eye-slash"
            @click="retire(props.row)"
          >
            <q-tooltip>{{ $t('carriers.retire') }}</q-tooltip>
          </q-btn>
          <q-btn
            :aria-label="$t('carriers.reactivate')"
            v-else
            flat
            round
            dense
            icon="ph:eye"
            @click="restore(props.row)"
          >
            <q-tooltip>{{ $t('carriers.reactivate') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('carriers.none') }}</div>
      </template>
    </q-table>

    <q-dialog
      :model-value="dialog"
      :persistent="guard.persistent.value"
      @update:model-value="guard.onToggle"
    >
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editId ? $t('carriers.edit_title') : $t('carriers.new_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              :label="$t('carriers.name')"
              outlined
              dense
              autofocus
              :rules="[(v: string) => !!v.trim() || $t('carriers.name_rule')]"
            />
            <q-input
              v-model="form.code"
              :label="$t('carriers.code')"
              :hint="$t('carriers.code_hint')"
              outlined
              dense
              :rules="[(v: string) => !!v.trim() || $t('carriers.code_rule')]"
            />
            <q-input
              v-model="form.tracking_url_template"
              :label="$t('carriers.template')"
              :hint="$t('carriers.template_hint')"
              outlined
              dense
              clearable
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="guard.requestClose()" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  createCarrier,
  listCarriers,
  retireCarrier,
  updateCarrier,
  type Carrier,
} from '@/api/shipping';
import { extractApiError } from '@/api/errors';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';

const { t } = useI18n();

const carriers = ref<Carrier[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const showRetired = ref(false);

const rows = computed(() =>
  showRetired.value ? carriers.value : carriers.value.filter((c) => c.is_active),
);

const columns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('carriers.col_name'), field: 'name', align: 'left' },
  { name: 'code', label: t('carriers.col_code'), field: 'code', align: 'left' },
  {
    name: 'template',
    label: t('carriers.col_link'),
    field: 'tracking_url_template',
    align: 'left',
  },
  { name: 'active', label: t('carriers.col_state'), field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    carriers.value = await listCarriers(true);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editId = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive<{ name: string; code: string; tracking_url_template: string | null }>({
  name: '',
  code: '',
  tracking_url_template: '',
});

// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const snapshot = useFormSnapshot(() => form);
const guard = useDialogGuard({
  isOpen: () => dialog.value,
  close: () => (dialog.value = false),
  isDirty: snapshot.isDirty,
});

function openCreate() {
  editId.value = null;
  form.name = '';
  form.code = '';
  form.tracking_url_template = '';
  dialogError.value = null;
  snapshot.take();
  dialog.value = true;
}

function openEdit(c: Carrier) {
  editId.value = c.id;
  form.name = c.name;
  form.code = c.code;
  form.tracking_url_template = c.tracking_url_template ?? '';
  dialogError.value = null;
  snapshot.take();
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  const payload = {
    name: form.name.trim(),
    code: form.code.trim(),
    // q-input clearable sets null; the API stores blank as "no tracking page".
    tracking_url_template: (form.tracking_url_template ?? '').trim() || null,
  };
  try {
    if (editId.value) {
      await updateCarrier(editId.value, payload);
    } else {
      await createCarrier(payload);
    }
    dialog.value = false;
    notice.value = t('carriers.saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function retire(c: Carrier) {
  error.value = null;
  try {
    await retireCarrier(c.id);
    notice.value = `${c.name} retiré du sélecteur.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.op_failed');
  }
}

async function restore(c: Carrier) {
  error.value = null;
  try {
    await updateCarrier(c.id, { is_active: true });
    notice.value = `${c.name} réactivé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.op_failed');
  }
}

watch(showRetired, () => {
  notice.value = null;
});

onMounted(load);
</script>
