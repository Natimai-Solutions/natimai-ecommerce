<template>
  <q-page class="admin-page">
    <PageHeader title="Avoirs">
      <template #hint>
        Un avoir est émis automatiquement à chaque remboursement, en correction de la facture
        d'origine : une facture émise n'est jamais modifiée. La numérotation
        <span class="font-mono">AV-AAAA-NNNNN</span> est continue par exercice, distincte de celle
        des factures.
      </template>
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
          icon="ph:download-simple"
          label="Export comptable (CSV)"
          :loading="exporting"
          @click="onExport"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-select
        v-model="fiscalYear"
        :options="yearOptions"
        label="Exercice"
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
        <span class="text-subtle">Aucun avoir{{ fiscalYear ? ' pour cet exercice' : '' }}.</span>
      </template>
    </q-table>

    <p v-if="rows.length" class="text-caption text-subtle q-mt-sm q-mb-none">
      {{ rows.length }} avoir(s) — montants crédités, en positif ; le document porte le sens.
    </p>
  </q-page>
</template>

<script setup lang="ts">
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
