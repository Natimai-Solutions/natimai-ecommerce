<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('currency_rates.title')">
      <template #hint>
        <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
        <span v-html="$t('currency_rates.explain')"></span>
      </template>
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
          :label="$t('currency_rates.add')"
          data-testid="currency-add"
          @click="openAdd"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div class="currency-display">
      <q-select
        :model-value="display.default_display_currency"
        :options="defaultOptions"
        :label="$t('currency_rates.default_display')"
        :hint="$t('currency_rates.default_display_hint', { ref: display.reference_currency })"
        outlined
        dense
        emit-value
        map-options
        :loading="savingDefault"
        class="currency-display__select"
        data-testid="currency-default-display"
        @update:model-value="saveDefault"
      />
      <p class="admin-hint currency-display__note">{{ $t('currency_rates.hidden_note') }}</p>
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
          <StatusTag
            v-if="!props.row.valid_until"
            :label="$t('currency_rates.active')"
            tone="ok"
            icon="ph:check-circle"
          />
          <span v-else>{{ props.row.valid_until }}</span>
        </q-td>
      </template>
      <template #body-cell-offered="props">
        <q-td :props="props">
          <StatusTag
            :label="
              isHidden(props.row.currency_code)
                ? $t('currency_rates.st_hidden')
                : $t('currency_rates.st_offered')
            "
            :tone="isHidden(props.row.currency_code) ? 'neutral' : 'ok'"
            :icon="isHidden(props.row.currency_code) ? 'ph:eye-slash' : 'ph:eye'"
            :data-testid="`currency-offered-${props.row.currency_code}`"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="currency-actions">
          <q-btn
            v-if="!props.row.valid_until"
            flat
            dense
            no-caps
            :icon="isHidden(props.row.currency_code) ? 'ph:eye' : 'ph:eye-slash'"
            :label="
              isHidden(props.row.currency_code)
                ? $t('currency_rates.offer')
                : $t('currency_rates.hide')
            "
            :loading="togglingCode === props.row.currency_code"
            :data-testid="`currency-toggle-${props.row.currency_code}`"
            @click="toggleDisplay(props.row.currency_code)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="ph:pencil-simple"
            :label="$t('currency_rates.update')"
            @click="openEdit(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">
          {{ $t('currency_rates.none') }}
        </div>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{
              editing
                ? $t('currency_rates.new_rate', { code: editing.currency_code })
                : $t('currency_rates.add')
            }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-if="!editing"
              v-model="editForm.currency_code"
              :label="$t('currency_rates.code')"
              :hint="$t('currency_rates.code_hint')"
              outlined
              dense
              maxlength="3"
              class="font-mono"
              data-testid="currency-code"
              :rules="[(v: string) => /^[A-Za-z]{3}$/.test(v) || $t('currency_rates.code_rule')]"
              @update:model-value="(v) => (editForm.currency_code = String(v ?? '').toUpperCase())"
            />
            <q-input
              v-model="editForm.rate_to_reference"
              :label="$t('currency_rates.rate')"
              type="number"
              step="0.000001"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="editForm.valid_from"
              :label="$t('currency_rates.valid_from')"
              type="date"
              outlined
              dense
              :rules="req"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
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
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  listCurrencyRates,
  setCurrencyDisplay,
  setDefaultDisplayCurrency,
  upsertCurrencyRate,
  type CurrencyDisplaySettings,
  type CurrencyRate,
} from '@/api/currencyRates';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<CurrencyRate[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

// --- Display currencies (R9 / T2): offered to the visitor, default ---
const display = ref<CurrencyDisplaySettings>({
  reference_currency: '',
  default_display_currency: '',
  hidden_display_currencies: [],
});
const savingDefault = ref(false);
const togglingCode = ref<string | null>(null);

function isHidden(code: string): boolean {
  return display.value.hidden_display_currencies.includes(code.toUpperCase());
}

/** The reference currency, then every offered currency with an open rate. */
const defaultOptions = computed(() => {
  const codes = new Set<string>([display.value.reference_currency]);
  for (const r of rows.value) {
    if (!r.valid_until && !isHidden(r.currency_code)) codes.add(r.currency_code);
  }
  return [...codes].filter(Boolean).map((code) => ({ value: code, label: code }));
});

async function saveDefault(code: string) {
  if (!code || code === display.value.default_display_currency) return;
  savingDefault.value = true;
  error.value = null;
  notice.value = null;
  try {
    display.value = await setDefaultDisplayCurrency(code);
    notice.value = t('currency_rates.default_saved', { code });
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    savingDefault.value = false;
  }
}

async function toggleDisplay(code: string) {
  togglingCode.value = code;
  error.value = null;
  notice.value = null;
  try {
    const hidden = isHidden(code);
    display.value = await setCurrencyDisplay(code, hidden);
    notice.value = t(hidden ? 'currency_rates.offered_done' : 'currency_rates.hidden_done', {
      code,
    });
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    togglingCode.value = null;
  }
}

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'currency_code',
    label: t('currency_rates.col_currency'),
    field: 'currency_code',
    align: 'left',
  },
  {
    name: 'rate_to_reference',
    label: t('currency_rates.col_rate'),
    field: 'rate_to_reference',
    align: 'left',
  },
  { name: 'valid_from', label: t('currency_rates.col_from'), field: 'valid_from', align: 'left' },
  {
    name: 'valid_until',
    label: t('currency_rates.col_until'),
    field: 'valid_until',
    align: 'left',
  },
  { name: 'source', label: t('currency_rates.col_source'), field: 'source', align: 'left' },
  {
    name: 'offered',
    label: t('currency_rates.col_offered'),
    field: 'currency_code',
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const response = await listCurrencyRates();
    rows.value = response.data;
    display.value = {
      reference_currency: response.reference_currency,
      default_display_currency: response.default_display_currency,
      hidden_display_currencies: response.hidden_display_currencies,
    };
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

const editDialog = ref(false);
const editing = ref<CurrencyRate | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editForm = reactive({ currency_code: '', rate_to_reference: '', valid_from: '' });

function openEdit(rate: CurrencyRate) {
  dialogError.value = null;
  editing.value = rate;
  editForm.currency_code = rate.currency_code;
  editForm.rate_to_reference = rate.rate_to_reference;
  editForm.valid_from = new Date().toISOString().slice(0, 10);
  editDialog.value = true;
}

/** A new currency is a first rate on a new code (offered to the visitor at once). */
function openAdd() {
  dialogError.value = null;
  editing.value = null;
  editForm.currency_code = '';
  editForm.rate_to_reference = '';
  editForm.valid_from = new Date().toISOString().slice(0, 10);
  editDialog.value = true;
}

async function submitEdit() {
  const code = (editing.value?.currency_code ?? editForm.currency_code).trim().toUpperCase();
  if (!code) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await upsertCurrencyRate(code, {
      rate_to_reference: editForm.rate_to_reference,
      valid_from: editForm.valid_from,
    });
    editDialog.value = false;
    notice.value = editing.value
      ? t('currency_rates.rate_saved', { code })
      : t('currency_rates.added', { code });
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.currency-display {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 24px;
  margin-bottom: 16px;
}

.currency-display__select {
  min-width: 260px;
}

.currency-display__note {
  flex: 1 1 320px;
  margin: 0;
}

.currency-actions {
  white-space: nowrap;
}
</style>
