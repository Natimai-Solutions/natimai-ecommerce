<template>
  <q-page class="admin-page">
    <PageHeader
      title="Commandes"
      hint="Commandes passées sur la boutique, les plus récentes d'abord."
    >
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-select
        v-model="departureFilter"
        :options="departureOptions"
        label="Départ groupé"
        dense
        outlined
        emit-value
        map-options
        clearable
        style="min-width: 260px"
        @update:model-value="load"
      />
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading && rows.length === 0" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <div v-else-if="rows.length === 0" class="app-empty">
      <q-icon name="ph:receipt" size="28px" class="text-subtle" />
      <h3>Aucune commande</h3>
      <p v-if="departureFilter">Aucune commande pour ce filtre.</p>
    </div>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      row-key="order_id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
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
            :tone="toneOf(orderStatusColor(props.row.status))"
            :icon="toneIcon(toneOf(orderStatusColor(props.row.status)))"
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
            label="Ouvrir"
            :to="`/orders/${props.row.order_id}`"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import { formatMoney as money } from '@app/utils';
import { useShopConfigStore } from '@/stores/shopConfig';
import PageHeader from '@/components/PageHeader.vue';
import {
  listOrders,
  orderStatusColor,
  orderStatusLabel,
  type AdminOrderListItem,
} from '@/api/orders';
import { extractApiError } from '@/api/errors';
import { listDepartures, type Departure } from '@/api/departures';

const rows = ref<AdminOrderListItem[]>([]);
// null = all orders, 'none' = orders without a departure, otherwise a departure id.
const departureFilter = ref<string | null>(null);
const departures = ref<Departure[]>([]);
const departureOptions = computed(() => [
  { label: 'Sans départ groupé', value: 'none' },
  ...departures.value.map((d) => ({
    label: `${d.name} (${formatDate(d.order_cutoff_at)})`,
    value: d.id,
  })),
]);
const loading = ref(false);
const error = ref<string | null>(null);

const shopConfig = useShopConfigStore();

/** Amount in its own currency (the order's), else the reference currency. */
function formatMoney(amount: number, currency?: string | null): string {
  return Number.isFinite(amount) ? money(amount, currency || shopConfig.currency) : String(amount);
}

function formatDate(raw: string | null): string {
  if (!raw) return '—';
  const d = new Date(raw);
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

const columns: QTableColumn[] = [
  { name: 'order', label: 'Commande', field: 'order_id', align: 'left' },
  {
    name: 'created_at',
    label: 'Date',
    field: 'created_at',
    align: 'left',
    format: (v: string | null) => formatDate(v),
  },
  { name: 'client', label: 'Client', field: 'user_id', align: 'left' },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'total', label: 'Total', field: 'total_amount', align: 'right' },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const filter = departureFilter.value;
    rows.value = await listOrders(
      filter === 'none' ? { unassigned: true } : { departure_id: filter },
    );
    if (departures.value.length === 0) {
      departures.value = await listDepartures().catch(() => []);
    }
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>
