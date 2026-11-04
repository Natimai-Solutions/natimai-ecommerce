<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('tax.title')" :hint="$t('tax.hint')">
      <template #actions>
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
          :label="$t('tax.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <section class="app-section" aria-labelledby="tax-settings-title">
      <div class="app-section__head">
        <h2 id="tax-settings-title" class="app-section__title">{{ $t('tax.applied') }}</h2>
      </div>
      <p class="admin-hint">
        <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
        <span v-html="$t('tax.intro')"></span>
      </p>
      <AppNotice v-if="settingsNotice" tone="success" dense class="q-mb-sm">
        {{ settingsNotice }}
      </AppNotice>
      <AppNotice v-if="settingsError" tone="error" dense class="q-mb-sm">
        {{ settingsError }}
      </AppNotice>
      <div class="tax-settings">
        <q-select
          v-model="settingsForm.default_code"
          :options="codeOptions"
          :label="$t('tax.default_rate')"
          outlined
          dense
          emit-value
          map-options
          data-testid="tax-default-code"
        />
        <q-select
          v-model="settingsForm.fees_code"
          :options="codeOptions"
          :label="$t('tax.fees_rate')"
          outlined
          dense
          emit-value
          map-options
          data-testid="tax-fees-code"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          :label="$t('common.save')"
          :loading="savingSettings"
          :disable="!settingsChanged"
          data-testid="tax-settings-save"
          @click="saveSettings"
        />
      </div>
    </section>

    <div class="app-section__head q-mt-lg">
      <h2 class="app-section__title">{{ $t('tax.all') }}</h2>
    </div>
    <div class="admin-toolbar">
      <q-input
        v-model="territory"
        :label="$t('tax.territory_filter')"
        outlined
        dense
        clearable
        @update:model-value="load"
      />
      <q-select
        v-model="validFilter"
        :options="validOptions"
        :label="$t('tax.validity')"
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
        <q-td :props="props">
          <span class="font-mono">{{ props.row.code }}</span>
          <StatusTag
            v-if="settings && props.row.code === settings.default_code"
            :label="$t('tax.default')"
            tone="ok"
            icon="ph:star"
            class="q-ml-xs"
          />
          <StatusTag
            v-if="settings && props.row.code === settings.fees_code"
            :label="$t('tax.fees')"
            tone="neutral"
            icon="ph:receipt"
            class="q-ml-xs"
          />
        </q-td>
      </template>
      <template #body-cell-rate="props">
        <q-td :props="props" class="font-mono">{{ props.row.rate_pct }} %</q-td>
      </template>
      <template #body-cell-valid_until="props">
        <q-td :props="props">
          <StatusTag
            v-if="!props.row.valid_until"
            :label="$t('tax.active')"
            tone="ok"
            icon="ph:check-circle"
          />
          <span v-else>{{ props.row.valid_until }}</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('tax.edit') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('tax.none') }}</div>
      </template>
    </q-table>

    <!-- Create dialog -->
    <q-dialog
      :model-value="createDialog"
      :persistent="createGuard.persistent.value"
      @update:model-value="createGuard.onToggle"
    >
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('tax.new_title') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.code"
              :label="$t('tax.code')"
              :hint="$t('tax.code_hint')"
              outlined
              dense
              :rules="req"
            />
            <q-input v-model="form.label" :label="$t('tax.label')" outlined dense :rules="req" />
            <q-input
              v-model="form.rate_pct"
              :label="$t('tax.rate')"
              type="number"
              step="0.01"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.territory_code"
              :label="$t('tax.territory')"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.valid_from"
              :label="$t('tax.valid_from')"
              type="date"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.valid_until"
              :label="$t('tax.valid_until')"
              type="date"
              outlined
              dense
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="createGuard.requestClose()" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('tax.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Edit dialog (label + valid_until only) -->
    <q-dialog
      :model-value="editDialog"
      :persistent="editGuard.persistent.value"
      @update:model-value="editGuard.onToggle"
    >
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('tax.edit_title', { code: editing?.code }) }}</h2>
          <p class="app-dialog__text">
            {{ $t('tax.immutable', { rate: editing?.rate_pct }) }}
          </p>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input v-model="editForm.label" :label="$t('tax.label_short')" outlined dense />
            <q-input
              v-model="editForm.valid_until"
              :label="$t('tax.close_on')"
              type="date"
              outlined
              dense
              clearable
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="editGuard.requestClose()" />
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
import { intlLocale, todayLocal } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  createTaxRate,
  getTaxSettings,
  listTaxRates,
  updateTaxRate,
  updateTaxSettings,
  type TaxRate,
  type TaxSettings,
} from '@/api/taxRates';
import { useShopConfigStore } from '@/stores/shopConfig';
import { extractApiError } from '@/api/errors';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';

const { t } = useI18n();

const shopConfig = useShopConfigStore();
const shopTerritory = computed(() => shopConfig.config?.tax_territory_code ?? 'PF');

// --- Default rate and fees rate ---------------------------------------------
const settings = ref<TaxSettings | null>(null);
const inForce = ref<TaxRate[]>([]);
const settingsForm = reactive({ default_code: '', fees_code: '' });
const savingSettings = ref(false);
const settingsNotice = ref<string | null>(null);
const settingsError = ref<string | null>(null);

/** One option per code in force in the shop's territory. */
const codeOptions = computed(() => {
  const seen = new Map<string, TaxRate>();
  for (const rate of inForce.value) {
    if (rate.territory_code === shopTerritory.value && !seen.has(rate.code)) {
      seen.set(rate.code, rate);
    }
  }
  return [...seen.values()].map((rate) => ({
    value: rate.code,
    label: `${rate.label} — ${Number(rate.rate_pct).toLocaleString(intlLocale())} %`,
  }));
});
const settingsChanged = computed(
  () =>
    !!settings.value &&
    (settingsForm.default_code !== settings.value.default_code ||
      settingsForm.fees_code !== settings.value.fees_code),
);

async function loadSettings() {
  settingsError.value = null;
  try {
    const [current, rates] = await Promise.all([getTaxSettings(), listTaxRates({ valid: true })]);
    settings.value = current;
    inForce.value = rates;
    settingsForm.default_code = current.default_code;
    settingsForm.fees_code = current.fees_code;
  } catch (err) {
    settingsError.value = extractApiError(err) ?? t('common.load_failed');
  }
}

async function saveSettings() {
  savingSettings.value = true;
  settingsNotice.value = null;
  settingsError.value = null;
  try {
    settings.value = await updateTaxSettings({ ...settingsForm });
    settingsNotice.value = t('tax.saved');
  } catch (err) {
    settingsError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    savingSettings.value = false;
  }
}

const rows = ref<TaxRate[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const territory = ref<string | null>(null);
const validFilter = ref<boolean | null>(null);

const validOptions = computed(() => [
  { label: t('tax.opt_all'), value: null },
  { label: t('tax.opt_active'), value: true },
  { label: t('tax.opt_expired'), value: false },
]);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];

const columns = computed<QTableColumn[]>(() => [
  { name: 'code', label: t('tax.col_code'), field: 'code', align: 'left' },
  { name: 'label', label: t('tax.col_label'), field: 'label', align: 'left' },
  { name: 'rate', label: t('tax.col_rate'), field: 'rate_pct', align: 'left' },
  { name: 'territory_code', label: t('tax.col_territory'), field: 'territory_code', align: 'left' },
  { name: 'valid_from', label: t('tax.col_from'), field: 'valid_from', align: 'left' },
  { name: 'valid_until', label: t('tax.col_until'), field: 'valid_until', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const params: { territory_code?: string; valid?: boolean } = {};
    if (territory.value) params.territory_code = territory.value;
    if (validFilter.value !== null) params.valid = validFilter.value;
    rows.value = await listTaxRates(params);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
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
  territory_code: '',
  valid_from: '',
  valid_until: '',
});
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const createSnapshot = useFormSnapshot(() => form);
const createGuard = useDialogGuard({
  isOpen: () => createDialog.value,
  close: () => (createDialog.value = false),
  isDirty: createSnapshot.isDirty,
});

function openCreate() {
  dialogError.value = null;
  form.code = '';
  form.label = '';
  form.rate_pct = '';
  form.territory_code = shopTerritory.value;
  form.valid_from = todayLocal();
  form.valid_until = '';
  createSnapshot.take();
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
    await Promise.all([load(), loadSettings()]);
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('tax.create_failed');
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
const editSnapshot = useFormSnapshot(() => editForm);
const editGuard = useDialogGuard({
  isOpen: () => editDialog.value,
  close: () => (editDialog.value = false),
  isDirty: editSnapshot.isDirty,
});

function openEdit(rate: TaxRate) {
  dialogError.value = null;
  editing.value = rate;
  editForm.label = rate.label;
  editForm.valid_until = rate.valid_until ?? '';
  editSnapshot.take();
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
    dialogError.value = extractApiError(err) ?? t('tax.edit_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadSettings();
});
</script>

<style scoped>
.tax-settings {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  max-width: 820px;
}

@media (max-width: 599px) {
  .tax-settings {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
