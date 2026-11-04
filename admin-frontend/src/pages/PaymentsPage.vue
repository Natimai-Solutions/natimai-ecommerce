<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('payments_list.title')" :hint="$t('payments_list.hint')">
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
      <q-input
        :aria-label="$t('payments_list.search')"
        v-model="filters.q"
        dense
        outlined
        clearable
        :placeholder="$t('payments_list.search')"
        class="admin-toolbar__search"
        data-testid="payments-search"
        @keyup.enter="reload"
        @clear="reload"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-select
        v-model="filters.status"
        dense
        outlined
        clearable
        emit-value
        map-options
        :options="statusOptions"
        :label="$t('payments_list.status')"
        class="admin-toolbar__select"
        data-testid="payments-status"
        @update:model-value="reload"
      />
      <q-select
        v-model="filters.provider_code"
        dense
        outlined
        clearable
        emit-value
        map-options
        :options="providerOptions"
        :label="$t('payments_list.provider')"
        class="admin-toolbar__select"
        @update:model-value="reload"
      />
      <q-input
        v-model="filters.date_from"
        dense
        outlined
        clearable
        type="date"
        :label="$t('payments_list.from')"
        class="admin-toolbar__date"
        @update:model-value="reload"
      />
      <q-input
        v-model="filters.date_to"
        dense
        outlined
        clearable
        type="date"
        :label="$t('payments_list.to')"
        class="admin-toolbar__date"
        @update:model-value="reload"
      />
    </div>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading && rows.length === 0" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <div v-else-if="rows.length === 0" class="app-empty">
      <q-icon name="ph:receipt" size="28px" class="text-subtle" />
      <h3>{{ $t('payments_list.none') }}</h3>
      <p>{{ $t('payments_list.none_hint') }}</p>
    </div>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      row-key="payment_id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
      data-testid="payments-table"
    >
      <template #body-cell-created_at="props">
        <q-td :props="props" class="text-no-wrap">
          {{ props.row.created_at ? formatDateTime(props.row.created_at) : '—' }}
        </q-td>
      </template>
      <template #body-cell-provider="props">
        <q-td :props="props">
          <div>{{ props.row.method_name || providerLabel(props.row.provider_code) }}</div>
          <div class="text-caption text-subtle font-mono">{{ props.row.provider_code }}</div>
        </q-td>
      </template>
      <template #body-cell-amount="props">
        <q-td :props="props">
          <div class="font-mono text-weight-medium">
            {{ formatMoney(props.row.amount, props.row.currency) }}
          </div>
          <div
            v-if="props.row.received_amount > 0 && props.row.received_amount < props.row.amount"
            class="text-caption text-warning"
          >
            {{
              $t('payments_list.received', {
                amount: formatMoney(props.row.received_amount, props.row.currency),
              })
            }}
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            v-if="props.row.status"
            :tone="paymentStatusTone(props.row.status)"
            :icon="toneIcon(paymentStatusTone(props.row.status))"
            :label="statusLabel(props.row.status)"
          />
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-reference="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-customer="props">
        <q-td :props="props">
          <div :title="props.row.user_id">
            {{ props.row.user_name || props.row.user_email || props.row.user_id.slice(0, 8) }}
          </div>
          <div v-if="props.row.user_name && props.row.user_email" class="text-caption text-subtle">
            {{ props.row.user_email }}
          </div>
        </q-td>
      </template>
      <template #body-cell-order="props">
        <q-td :props="props">
          <router-link
            v-if="props.row.order_id"
            :to="`/orders/${props.row.order_id}`"
            class="admin-link font-mono"
            :title="props.row.order_id"
            >{{ props.row.order_number ?? `#${props.row.order_id.slice(0, 8)}` }}</router-link
          >
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
    </q-table>

    <div v-if="count > PAGE_SIZE" class="admin-pagination">
      <span class="text-subtle">
        {{
          $t('payments_list.page_info', {
            from: page * PAGE_SIZE + 1,
            to: Math.min((page + 1) * PAGE_SIZE, count),
            count,
          })
        }}
      </span>
      <q-btn
        flat
        dense
        no-caps
        icon="ph:caret-left"
        :disable="page === 0"
        @click="goTo(page - 1)"
      />
      <q-btn
        flat
        dense
        no-caps
        icon="ph:caret-right"
        :disable="(page + 1) * PAGE_SIZE >= count"
        @click="goTo(page + 1)"
      />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import type { QTableColumn } from 'quasar';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, type StatusTone } from '@app/ui/statusTone';
import { formatDateTime, formatMoney as money } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { listPayments, type PaymentRow } from '@/api/payments';
import { useShopConfigStore } from '@/stores/shopConfig';
import { providerLabel } from '@/utils/payments';

/**
 * Every payment of the shop (A19): the ledger behind « Validation des
 * paiements », which only shows what waits for an admin.
 */
const i18n = useI18n();
const { t } = i18n;
const shopConfig = useShopConfigStore();

const PAGE_SIZE = 50;
const rows = ref<PaymentRow[]>([]);
const count = ref(0);
const page = ref(0);
const statuses = ref<string[]>([]);
const providerCodes = ref<string[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const route = useRoute();
// The dashboard links here with a status preselected (?status=Authorized).
const initialStatus = typeof route.query.status === 'string' ? route.query.status : null;
const filters = reactive({
  q: '',
  status: initialStatus,
  provider_code: null as string | null,
  date_from: null as string | null,
  date_to: null as string | null,
});

const PAYMENT_STATUS_TONES: Record<string, StatusTone> = {
  Completed: 'ok',
  DepositPaid: 'ok',
  Authorized: 'warn',
  AwaitingValidation: 'warn',
  DocumentRequired: 'warn',
  DocumentUploaded: 'warn',
  UnderReview: 'warn',
  Failed: 'danger',
};
/** Encaissé : ok ; à capturer ou à valider : warn ; refusé : danger ; le reste
 * est neutre : clos sans incident (annulé, remboursé) ou simplement en attente
 * (« Pending », l'état de repos de tout formulaire de carte ouvert puis
 * abandonné : une alerte là-dessus noierait celles qui comptent). */
function paymentStatusTone(status: string): StatusTone {
  return PAYMENT_STATUS_TONES[status] ?? 'neutral';
}

/** The order screens already translate the payment statuses; reuse them. */
function statusLabel(status: string): string {
  const key = `payment_status.${status}`;
  return i18n.te(key) ? t(key) : status;
}

const statusOptions = computed(() =>
  statuses.value.map((status) => ({ label: statusLabel(status), value: status })),
);
const providerOptions = computed(() =>
  providerCodes.value.map((code) => ({ label: providerLabel(code), value: code })),
);

const columns = computed<QTableColumn[]>(() => [
  { name: 'created_at', label: t('payments_list.col_date'), field: 'created_at', align: 'left' },
  { name: 'provider', label: t('payments_list.col_method'), field: 'provider_code', align: 'left' },
  { name: 'amount', label: t('payments_list.col_amount'), field: 'amount', align: 'right' },
  { name: 'status', label: t('payments_list.col_status'), field: 'status', align: 'left' },
  {
    name: 'reference',
    label: t('payments_list.col_reference'),
    field: (r: PaymentRow) => r.provider_reference ?? '—',
    align: 'left',
  },
  { name: 'customer', label: t('payments_list.col_customer'), field: 'user_id', align: 'left' },
  { name: 'order', label: t('payments_list.col_order'), field: 'order_id', align: 'left' },
]);

function formatMoney(amount: number, currency?: string | null): string {
  return Number.isFinite(amount) ? money(amount, currency || shopConfig.currency) : String(amount);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const result = await listPayments({
      q: filters.q.trim() || undefined,
      status: filters.status,
      provider_code: filters.provider_code,
      date_from: filters.date_from,
      date_to: filters.date_to,
      skip: page.value * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
    rows.value = result.data;
    count.value = result.count;
    statuses.value = result.statuses;
    providerCodes.value = result.provider_codes;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function reload() {
  page.value = 0;
  void load();
}

function goTo(next: number) {
  page.value = Math.max(0, next);
  void load();
}

onMounted(load);
</script>

<style scoped lang="scss">
.admin-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.admin-toolbar__search {
  flex: 1 1 240px;
}

.admin-toolbar__select {
  flex: 0 1 200px;
}

.admin-toolbar__date {
  flex: 0 1 170px;
}

.admin-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
</style>
