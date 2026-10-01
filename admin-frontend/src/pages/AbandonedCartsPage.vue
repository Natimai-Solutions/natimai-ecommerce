<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('abandoned.title')">
      <template #hint>
        {{
          $t('abandoned.hint', {
            hours: response?.reminder_delay_hours ?? '—',
            days: response?.reminder_max_age_days ?? '—',
          })
        }}
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
      </template>
    </PageHeader>

    <div class="cart-tiles">
      <div v-for="tile in tiles" :key="tile.label" class="app-panel cart-tile">
        <span class="cart-tile__label">{{ tile.label }}</span>
        <span class="cart-tile__value font-mono">{{ tile.value }}</span>
        <span class="cart-tile__hint">{{ tile.hint }}</span>
      </div>
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="cart_id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-customer="props">
        <q-td :props="props">
          <div>{{ props.row.user_name || '—' }}</div>
          <div class="text-caption text-muted">{{ props.row.user_email }}</div>
        </q-td>
      </template>
      <template #body-cell-items="props">
        <q-td :props="props">
          <div v-for="line in props.row.items.slice(0, 3)" :key="line.product_id" class="ellipsis">
            {{ line.quantity }} × {{ line.name }}
          </div>
          <div v-if="props.row.items.length > 3" class="text-caption text-muted">
            {{ $t('abandoned.more', { n: props.row.items.length - 3 }) }}
          </div>
        </q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props" class="font-mono">{{ props.value }}</q-td>
      </template>
      <template #body-cell-reminded="props">
        <q-td :props="props" align="center">
          <StatusTag
            v-if="props.row.reminded_at"
            tone="ok"
            icon="ph:paper-plane-tilt"
            :label="$t('abandoned.reminded_on', { date: formatDate(props.row.reminded_at) })"
          />
          <StatusTag v-else tone="neutral" icon="ph:clock" :label="$t('common.pending')" />
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{ $t('abandoned.none') }}</span>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { decimalsOf, intlLocale } from '@app/utils';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  listAbandonedCarts,
  type AbandonedCart,
  type AbandonedCartsResponse,
} from '@/api/abandonedCarts';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const response = ref<AbandonedCartsResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const rows = computed(() => response.value?.data ?? []);

const tiles = computed(() => {
  const c = response.value?.counters ?? { open: 0, reminded: 0, recovered: 0 };
  return [
    { label: t('abandoned.open'), value: c.open, hint: t('abandoned.open_hint') },
    { label: t('abandoned.reminded'), value: c.reminded, hint: t('abandoned.reminded_hint') },
    {
      label: t('abandoned.recovered'),
      value: c.recovered,
      hint: t('abandoned.recovered_hint'),
    },
  ];
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

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(intlLocale());
}

const columns = computed<QTableColumn<AbandonedCart>[]>(() => [
  { name: 'customer', label: t('abandoned.col_customer'), field: 'user_email', align: 'left' },
  { name: 'items', label: t('abandoned.col_items'), field: 'items_count', align: 'left' },
  {
    name: 'total',
    label: t('abandoned.col_total'),
    field: (row) => formatAmount(row.total_amount, row.currency),
    align: 'right',
    sortable: true,
  },
  {
    name: 'last_activity_at',
    label: t('abandoned.col_activity'),
    field: (row) => formatDate(row.last_activity_at),
    align: 'left',
    sortable: true,
  },
  { name: 'reminded', label: t('abandoned.col_reminder'), field: 'reminded_at', align: 'center' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    response.value = await listAbandonedCarts({ limit: 200 });
  } catch (err) {
    error.value = extractApiError(err) ?? t('abandoned.load_failed');
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.cart-tiles {
  margin-bottom: 24px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.cart-tile {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cart-tile__label {
  font-size: 13px;
  color: var(--n-ink-2);
}

.cart-tile__value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--n-ink);
}

.cart-tile__hint {
  font-size: 12px;
  color: var(--n-ink-3);
}
</style>
