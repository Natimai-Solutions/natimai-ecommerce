<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('orders.title')" :hint="$t('orders.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:download-simple"
          :label="$t('orders.export')"
          :loading="exporting"
          :disable="count === 0"
          data-testid="orders-export"
          @click="exportCsv"
        />
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
      <q-input
        v-model="search"
        dense
        outlined
        clearable
        debounce="300"
        :placeholder="$t('orders.search')"
        :aria-label="$t('orders.search')"
        class="admin-toolbar__search"
        data-testid="orders-search"
        @update:model-value="reload"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-select
        v-model="statusFilter"
        :options="statusOptions"
        :label="$t('orders.col_status')"
        dense
        outlined
        emit-value
        map-options
        clearable
        class="admin-toolbar__select"
        data-testid="orders-status"
        @update:model-value="reload"
      />
      <q-select
        v-model="departureFilter"
        :options="departureOptions"
        :label="$t('orders.departure')"
        dense
        outlined
        emit-value
        map-options
        clearable
        class="admin-toolbar__select"
        @update:model-value="reload"
      />
      <q-input
        v-model="dateFrom"
        dense
        outlined
        clearable
        type="date"
        :label="$t('orders.from')"
        class="admin-toolbar__date"
        @update:model-value="reload"
      />
      <q-input
        v-model="dateTo"
        dense
        outlined
        clearable
        type="date"
        :label="$t('orders.to')"
        class="admin-toolbar__date"
        @update:model-value="reload"
      />
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="!loading && count === 0 && !error" class="app-empty">
      <q-icon name="ph:receipt" size="28px" class="text-subtle" />
      <h3>{{ $t('orders.none') }}</h3>
      <p v-if="hasFilters">{{ $t('orders.none_filter') }}</p>
    </div>

    <q-table
      v-else
      v-model:pagination="pagination"
      :rows="rows"
      :columns="columns"
      row-key="order_id"
      :loading="loading"
      flat
      bordered
      dense
      :rows-per-page-options="[25, 50, 100, 200]"
      data-testid="orders-table"
      @request="onRequest"
    >
      <template #body-cell-order="props">
        <q-td :props="props">
          <router-link
            :to="`/orders/${props.row.order_id}`"
            class="admin-link font-mono"
            :title="props.row.order_id"
            >{{ props.row.order_number ?? `#${props.row.order_id.slice(0, 8)}` }}</router-link
          >
        </q-td>
      </template>
      <template #body-cell-client="props">
        <q-td :props="props">
          <div>
            {{ props.row.user_name || props.row.user_email || props.row.user_id.slice(0, 8) }}
            <q-btn
              v-if="props.row.user_email && search !== props.row.user_email"
              flat
              dense
              round
              size="sm"
              icon="ph:funnel"
              :aria-label="$t('orders.customer_orders')"
              @click="showCustomer(props.row.user_email)"
            >
              <q-tooltip>{{ $t('orders.customer_orders') }}</q-tooltip>
            </q-btn>
          </div>
          <div v-if="props.row.user_name && props.row.user_email" class="text-caption text-subtle">
            {{ props.row.user_email }}
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            :label="orderStatusLabel(props.row.status)"
            :tone="orderStatusTone(props.row.status)"
            :icon="toneIcon(orderStatusTone(props.row.status))"
          />
        </q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props" class="font-mono text-weight-medium">
          {{ formatMoney(props.row.total_amount, props.row.currency) }}
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="ph:arrow-right"
            :label="$t('common.open')"
            :to="`/orders/${props.row.order_id}`"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn, QTableProps } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon } from '@app/ui/statusTone';
import { dayBounds, formatDate, formatMoney as money } from '@app/utils';
import { useShopConfigStore } from '@/stores/shopConfig';
import PageHeader from '@/components/PageHeader.vue';
import {
  downloadOrdersCsv,
  listOrdersPage,
  listOrderStatuses,
  orderStatusTone,
  orderStatusLabel,
  type AdminOrderListItem,
  type OrderFilters,
  type OrderSort,
} from '@/api/orders';
import { extractApiError } from '@/api/errors';
import { listDepartures, type Departure } from '@/api/departures';

const { t } = useI18n();
const route = useRoute();

const rows = ref<AdminOrderListItem[]>([]);
const count = ref(0);
// `?q=` opens the list on a customer (link from another screen).
const search = ref<string | null>(typeof route.query.q === 'string' ? route.query.q : null);
const statusFilter = ref<string | null>(null);
// null = all orders, 'none' = orders without a departure, otherwise a departure id.
const departureFilter = ref<string | null>(null);
// Business days (YYYY-MM-DD) of the shop, sent as the bounds of those days.
const dateFrom = ref<string | null>(null);
const dateTo = ref<string | null>(null);
const statuses = ref<string[]>([]);
const departures = ref<Departure[]>([]);
const loading = ref(false);
const exporting = ref(false);
const error = ref<string | null>(null);
const pagination = ref({
  page: 1,
  rowsPerPage: 50,
  rowsNumber: 0,
  sortBy: 'created_at',
  descending: true,
});

const SORTABLE: Record<string, OrderSort> = {
  order: 'order_number',
  created_at: 'created_at',
  total: 'total_amount',
};

const statusOptions = computed(() =>
  statuses.value.map((s) => ({ label: orderStatusLabel(s), value: s })),
);
const departureOptions = computed(() => [
  { label: t('orders.no_departure'), value: 'none' },
  ...departures.value.map((d) => ({
    label: `${d.name} (${formatDate(d.order_cutoff_at)})`,
    value: d.id,
  })),
]);
const hasFilters = computed(
  () =>
    !!search.value ||
    !!statusFilter.value ||
    !!departureFilter.value ||
    !!dateFrom.value ||
    !!dateTo.value,
);

const shopConfig = useShopConfigStore();

/** Amount in its own currency (the order's), else the reference currency. */
function formatMoney(amount: number, currency?: string | null): string {
  return Number.isFinite(amount) ? money(amount, currency || shopConfig.currency) : String(amount);
}

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'order',
    label: t('orders.col_order'),
    field: 'order_number',
    align: 'left',
    sortable: true,
  },
  {
    name: 'created_at',
    label: t('orders.col_date'),
    field: 'created_at',
    align: 'left',
    sortable: true,
    format: (v: string | null) => formatDate(v),
  },
  { name: 'client', label: t('orders.col_customer'), field: 'user_id', align: 'left' },
  { name: 'status', label: t('orders.col_status'), field: 'status', align: 'left' },
  {
    name: 'total',
    label: t('orders.col_total'),
    field: 'total_amount',
    align: 'right',
    sortable: true,
  },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
]);

function filters(): OrderFilters {
  const departure = departureFilter.value;
  return {
    q: search.value?.trim() || null,
    status: statusFilter.value,
    departure_id: departure && departure !== 'none' ? departure : null,
    unassigned: departure === 'none',
    date_from: dateFrom.value ? dayBounds(dateFrom.value).start : null,
    date_to: dateTo.value ? dayBounds(dateTo.value).end : null,
  };
}

async function load() {
  loading.value = true;
  error.value = null;
  const { page, rowsPerPage, sortBy, descending } = pagination.value;
  try {
    const result = await listOrdersPage({
      ...filters(),
      skip: (page - 1) * rowsPerPage,
      limit: rowsPerPage,
      sort_by: SORTABLE[sortBy ?? ''] ?? 'created_at',
      descending,
    });
    rows.value = result.data;
    count.value = result.count;
    pagination.value = { ...pagination.value, rowsNumber: result.count };
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function reload() {
  pagination.value = { ...pagination.value, page: 1 };
  void load();
}

function onRequest(props: Parameters<NonNullable<QTableProps['onRequest']>>[0]) {
  const next = props.pagination;
  pagination.value = {
    ...pagination.value,
    page: next.page ?? 1,
    rowsPerPage: next.rowsPerPage || pagination.value.rowsPerPage,
    sortBy: next.sortBy ?? 'created_at',
    descending: next.sortBy ? Boolean(next.descending) : true,
  };
  void load();
}

function showCustomer(email: string) {
  search.value = email;
  reload();
}

async function exportCsv() {
  exporting.value = true;
  try {
    await downloadOrdersCsv(filters());
  } catch (err) {
    error.value = extractApiError(err) ?? t('orders.export_failed');
  } finally {
    exporting.value = false;
  }
}

onMounted(async () => {
  void load();
  [statuses.value, departures.value] = await Promise.all([
    listOrderStatuses().catch(() => []),
    listDepartures().catch(() => []),
  ]);
});
</script>

<style scoped>
.admin-toolbar__search {
  flex: 1 1 240px;
}

.admin-toolbar__select {
  flex: 0 1 220px;
}

.admin-toolbar__date {
  flex: 0 1 170px;
}
</style>
