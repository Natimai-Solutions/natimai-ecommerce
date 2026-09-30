<template>
  <q-page class="admin-page">
    <PageHeader title="Paniers abandonnés">
      <template #hint>
        Paniers ouverts (jamais commandés) des clients connectés. Un panier sans activité depuis
        {{ response?.reminder_delay_hours ?? '—' }} h reçoit un rappel par e-mail, une seule fois,
        si le client accepte les rappels commerciaux ; au-delà de
        {{ response?.reminder_max_age_days ?? '—' }} jours il n'est plus relancé.
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
            + {{ props.row.items.length - 3 }} autre(s)
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
            :label="`Relancé le ${formatDate(props.row.reminded_at)}`"
          />
          <StatusTag v-else tone="neutral" icon="ph:clock" label="En attente" />
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">Aucun panier abandonné.</span>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
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

const response = ref<AbandonedCartsResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const rows = computed(() => response.value?.data ?? []);

const tiles = computed(() => {
  const c = response.value?.counters ?? { open: 0, reminded: 0, recovered: 0 };
  return [
    { label: 'Paniers ouverts', value: c.open, hint: 'jamais commandés, avec au moins un article' },
    { label: 'Rappels envoyés', value: c.reminded, hint: 'depuis la mise en service' },
    {
      label: 'Récupérés',
      value: c.recovered,
      hint: 'commandés après le rappel — le seul chiffre qui compte',
    },
  ];
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

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('fr-FR');
}

const columns: QTableColumn<AbandonedCart>[] = [
  { name: 'customer', label: 'Client', field: 'user_email', align: 'left' },
  { name: 'items', label: 'Articles', field: 'items_count', align: 'left' },
  {
    name: 'total',
    label: 'Total',
    field: (row) => formatAmount(row.total_amount, row.currency),
    align: 'right',
    sortable: true,
  },
  {
    name: 'last_activity_at',
    label: 'Dernière activité',
    field: (row) => formatDate(row.last_activity_at),
    align: 'left',
    sortable: true,
  },
  { name: 'reminded', label: 'Rappel', field: 'reminded_at', align: 'center' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    response.value = await listAbandonedCarts({ limit: 200 });
  } catch (err) {
    error.value = extractApiError(err) ?? 'Impossible de charger les paniers.';
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
