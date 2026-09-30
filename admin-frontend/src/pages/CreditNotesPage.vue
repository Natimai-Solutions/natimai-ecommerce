<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Avoirs</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Un avoir est émis automatiquement à chaque remboursement, en correction de la facture
      d'origine : une facture émise n'est jamais modifiée. La numérotation AV-AAAA-NNNNN est
      continue par exercice, distincte de celle des factures.
    </div>

    <div class="row q-col-gutter-md q-mb-md items-end">
      <q-select
        v-model="fiscalYear"
        :options="yearOptions"
        label="Exercice"
        outlined
        dense
        emit-value
        map-options
        clearable
        class="col-12 col-sm-3"
        @update:model-value="load"
      />
      <div class="col-12 col-sm-auto">
        <q-btn
          color="primary"
          icon="download"
          label="Export comptable (CSV)"
          no-caps
          :loading="exporting"
          @click="onExport"
        />
      </div>
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-blue-1 text-blue-10 q-mb-md" dense rounded>
      {{ notice }}
    </q-banner>

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
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="picture_as_pdf"
            color="primary"
            label="PDF"
            :loading="downloadingId === props.row.id"
            @click="onDownload(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <div v-if="rows.length" class="text-caption text-grey-7 q-mt-sm">
      {{ rows.length }} avoir(s) — montants crédités, en positif ; le document porte le sens.
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  downloadCreditNotePdf,
  downloadCreditNotesCsv,
  listCreditNotes,
  type CreditNote,
} from '@/api/creditNotes';
import { extractApiError } from '@/api/errors';

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
  const digits = currency === 'XPF' ? 0 : 2;
  return `${amount.toLocaleString('fr-FR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${currency}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('fr-FR');
}

const columns: QTableColumn<CreditNote>[] = [
  {
    name: 'credit_note_number',
    label: 'N° avoir',
    field: 'credit_note_number',
    align: 'left',
    sortable: true,
  },
  {
    name: 'issued_at',
    label: 'Émis le',
    field: (row) => formatDate(row.issued_at),
    align: 'left',
    sortable: true,
  },
  {
    name: 'invoice_number',
    label: 'Facture corrigée',
    field: (row) => row.invoice_number ?? `#${row.invoice_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'order_number',
    label: 'Commande',
    field: (row) => row.order_number ?? `#${row.order_id.slice(0, 8)}`,
    align: 'left',
  },
  {
    name: 'reason',
    label: 'Motif',
    field: (row) => row.reason ?? '—',
    align: 'left',
    style: 'max-width: 320px; white-space: normal',
  },
  {
    name: 'total_excl_tax',
    label: 'HT crédité',
    field: (row) => formatAmount(row.total_excl_tax, row.currency),
    align: 'right',
  },
  {
    name: 'total_tax',
    label: 'Taxes',
    field: (row) => formatAmount(row.total_tax, row.currency),
    align: 'right',
  },
  {
    name: 'total_incl_tax',
    label: 'TTC crédité',
    field: (row) => formatAmount(row.total_incl_tax, row.currency),
    align: 'right',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listCreditNotes(
      fiscalYear.value ? { fiscal_year: fiscalYear.value } : undefined,
    );
  } catch (err) {
    error.value = extractApiError(err) ?? 'Impossible de charger les avoirs.';
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
    error.value = extractApiError(err) ?? 'Le téléchargement du PDF a échoué.';
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
    notice.value = 'Export généré.';
  } catch (err) {
    error.value = extractApiError(err) ?? "L'export comptable a échoué.";
  } finally {
    exporting.value = false;
  }
}

onMounted(load);
</script>
