<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('supplier_orders.title')" :hint="$t('supplier_orders.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-select
        v-model="statusFilter"
        :options="statusOptions"
        :label="$t('common.status')"
        outlined
        dense
        emit-value
        map-options
        clearable
        @update:model-value="load"
      />
      <q-input
        v-model="supplierFilter"
        :label="$t('supplier_orders.supplier_filter')"
        outlined
        dense
        clearable
        style="min-width: 260px"
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
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            :label="props.row.status"
            :tone="toneOf(statusColor(props.row.status))"
            :icon="toneIcon(toneOf(statusColor(props.row.status)))"
          />
        </q-td>
      </template>
      <template #body-cell-customer_order_number="props">
        <q-td :props="props">
          <span class="font-mono" :title="props.row.customer_order_number">{{
            props.row.customer_order_number.slice(0, 8)
          }}</span>
        </q-td>
      </template>
      <template #body-cell-supplier_order_number="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-attempts="props">
        <q-td :props="props" class="font-mono">{{ props.row.attempts }}</q-td>
      </template>
      <template #body-cell-error_message="props">
        <q-td :props="props">
          <span v-if="props.row.error_message" class="text-negative">{{
            props.row.error_message
          }}</span>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="ph:arrow-counter-clockwise"
            :label="$t('common.retry')"
            :loading="retryingId === props.row.id"
            :disable="props.row.status === 'submitted'"
            @click="onRetry(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">
          {{ $t('supplier_orders.none') }}
        </div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
import {
  listSupplierOrders,
  retrySupplierOrder,
  type SupplierOrder,
  type SupplierOrderStatus,
} from '@/api/supplierOrders';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<SupplierOrder[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const statusFilter = ref<SupplierOrderStatus | null>(null);
const supplierFilter = ref<string | null>(null);
const retryingId = ref<string | null>(null);

const statusOptions = computed(() => [
  { label: t('supplier_orders.st_pending'), value: 'pending' },
  { label: t('supplier_orders.st_submitted'), value: 'submitted' },
  { label: t('supplier_orders.st_error'), value: 'error' },
  { label: t('supplier_orders.st_skipped'), value: 'skipped' },
]);

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'created_at',
    label: t('supplier_orders.col_created'),
    field: 'created_at',
    align: 'left',
  },
  {
    name: 'supplier_name',
    label: t('supplier_orders.col_supplier'),
    field: 'supplier_name',
    align: 'left',
  },
  {
    name: 'customer_order_number',
    label: t('supplier_orders.col_order'),
    field: 'customer_order_number',
    align: 'left',
  },
  {
    name: 'supplier_order_number',
    label: t('supplier_orders.col_po'),
    field: (r) => r.supplier_order_number ?? '—',
    align: 'left',
  },
  { name: 'status', label: t('supplier_orders.col_status'), field: 'status', align: 'left' },
  {
    name: 'attempts',
    label: t('supplier_orders.col_attempts'),
    field: 'attempts',
    align: 'center',
  },
  {
    name: 'error_message',
    label: t('supplier_orders.st_error'),
    field: 'error_message',
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

function statusColor(status: SupplierOrderStatus): string {
  if (status === 'submitted') return 'green';
  if (status === 'error') return 'negative';
  if (status === 'pending') return 'orange';
  return 'blue-grey';
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const params: { status?: SupplierOrderStatus; supplier_name?: string } = {};
    if (statusFilter.value) params.status = statusFilter.value;
    if (supplierFilter.value) params.supplier_name = supplierFilter.value;
    const res = await listSupplierOrders(params);
    rows.value = res.data;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

async function onRetry(order: SupplierOrder) {
  retryingId.value = order.id;
  notice.value = null;
  error.value = null;
  try {
    const updated = await retrySupplierOrder(order.id);
    const idx = rows.value.findIndex((r) => r.id === updated.id);
    if (idx !== -1) rows.value[idx] = updated;
    notice.value =
      updated.status === 'submitted'
        ? t('supplier_orders.submitted', { number: updated.supplier_order_number ?? '—' })
        : t('supplier_orders.retried', {
            status: updated.status,
            error: updated.error_message ? ` — ${updated.error_message}` : '',
          });
  } catch (err) {
    error.value = extractApiError(err) ?? t('supplier_orders.retry_failed');
  } finally {
    retryingId.value = null;
  }
}

onMounted(load);
</script>
