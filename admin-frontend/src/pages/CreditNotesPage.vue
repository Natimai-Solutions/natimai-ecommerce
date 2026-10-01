<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('credit_notes.title')">
      <template #hint>
        <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
        <span v-html="$t('credit_notes.hint')"></span>
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
          icon="ph:download-simple"
          :label="$t('common.export_csv')"
          :loading="exporting"
          @click="onExport"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-select
        v-model="fiscalYear"
        :options="yearOptions"
        :label="$t('common.fiscal_year')"
        outlined
        dense
        emit-value
        map-options
        clearable
        @update:model-value="load"
      />
    </div>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="info" dense>{{ notice }}</AppNotice>
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
      <template #body-cell-credit_note_number="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-invoice_number="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-order_number="props">
        <q-td :props="props">
          <router-link
            :to="`/orders/${props.row.order_id}`"
            class="admin-link font-mono"
            :title="props.row.order_id"
            >{{ props.value }}</router-link
          >
        </q-td>
      </template>
      <template #body-cell-total_excl_tax="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-total_tax="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-total_incl_tax="props">
        <q-td :props="props" class="font-mono text-weight-medium">{{ props.value }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="ph:file-pdf"
            label="PDF"
            :loading="downloadingId === props.row.id"
            @click="onDownload(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{
          $t('credit_notes.none', { suffix: fiscalYear ? $t('common.for_year') : '' })
        }}</span>
      </template>
    </q-table>

    <p v-if="rows.length" class="text-caption text-subtle q-mt-sm q-mb-none">
      {{ $t('credit_notes.count', { n: rows.length }) }}
    </p>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { decimalsOf, intlLocale } from '@app/utils';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  downloadCreditNotePdf,
  downloadCreditNotesCsv,
  listCreditNotes,
  type CreditNote,
} from '@/api/creditNotes';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<CreditNote[]>([]);
const loading = ref(false);
const exporting = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const downloadingId = ref<string | null>(null);
const fiscalYear = ref<number | null>(null);

/** Current year plus the four previous ones — same window as the invoices. */
const yearOptions = computed(() => {
  const current = new Date().getFullYear();
  return Array.from({ length: 5 }, (_, index) => {
    const year = current - index;
    return { label: String(year), value: year };
  });
});

function formatAmount(value: string, currency: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  const digits = decimalsOf(currency);
  return `${amount.toLocaleString(intlLocale(), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${currency}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(intlLocale());
}

const columns = computed<QTableColumn<CreditNote>[]>(() => [
  {
    name: 'credit_note_number',
    label: t('credit_notes.col_number'),
    field: 'credit_note_number',
    align: 'left',
    sortable: true,
  },
  {
    name: 'issued_at',
    label: t('credit_notes.col_issued'),
    field: (row) => formatDate(row.issued_at),
    align: 'left',
    sortable: true,
  },
  {
    name: 'invoice_number',
    label: t('credit_notes.col_invoice'),
    field: (row) => row.invoice_number ?? `#${row.invoice_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'order_number',
    label: t('credit_notes.col_order'),
    field: (row) => row.order_number ?? `#${row.order_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'reason',
    label: t('credit_notes.col_reason'),
    field: (row) => row.reason ?? '—',
    align: 'left',
    style: 'max-width: 320px; white-space: normal',
  },
  {
    name: 'total_excl_tax',
    label: t('credit_notes.col_net'),
    field: (row) => formatAmount(row.total_excl_tax, row.currency),
    align: 'right',
  },
  {
    name: 'total_tax',
    label: t('credit_notes.col_tax'),
    field: (row) => formatAmount(row.total_tax, row.currency),
    align: 'right',
  },
  {
    name: 'total_incl_tax',
    label: t('credit_notes.col_gross'),
    field: (row) => formatAmount(row.total_incl_tax, row.currency),
    align: 'right',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listCreditNotes(
      fiscalYear.value ? { fiscal_year: fiscalYear.value } : undefined,
    );
  } catch (err) {
    error.value = extractApiError(err) ?? t('credit_notes.load_failed');
  } finally {
    loading.value = false;
  }
}

async function onDownload(note: CreditNote) {
  downloadingId.value = note.id;
  error.value = null;
  try {
    await downloadCreditNotePdf(note);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.pdf_failed');
  } finally {
    downloadingId.value = null;
  }
}

async function onExport() {
  exporting.value = true;
  error.value = null;
  notice.value = null;
  try {
    await downloadCreditNotesCsv(fiscalYear.value);
    notice.value = t('common.export_done');
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.export_failed');
  } finally {
    exporting.value = false;
  }
}

onMounted(load);
</script>
