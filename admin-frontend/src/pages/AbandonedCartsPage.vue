<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Paniers abandonnés</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Paniers ouverts (jamais commandés) des clients connectés. Un panier sans activité depuis
      {{ response?.reminder_delay_hours ?? '—' }} h reçoit un rappel par e-mail, une seule fois, si
      le client accepte les rappels commerciaux ; au-delà de
      {{ response?.reminder_max_age_days ?? '—' }} jours il n'est plus relancé.
    </div>

    <div class="row q-col-gutter-md q-mb-md">
      <div v-for="tile in tiles" :key="tile.label" class="col-12 col-sm-4">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-caption text-grey-7">{{ tile.label }}</div>
            <div class="text-h5">{{ tile.value }}</div>
            <div class="text-caption text-grey-6">{{ tile.hint }}</div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

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
          <div class="text-caption text-grey-7">{{ props.row.user_email }}</div>
        </q-td>
      </template>
      <template #body-cell-items="props">
        <q-td :props="props">
          <div v-for="line in props.row.items.slice(0, 3)" :key="line.product_id" class="ellipsis">
            {{ line.quantity }} × {{ line.name }}
          </div>
          <div v-if="props.row.items.length > 3" class="text-caption text-grey-7">
            + {{ props.row.items.length - 3 }} autre(s)
          </div>
        </q-td>
      </template>
      <template #body-cell-reminded="props">
        <q-td :props="props" align="center">
          <q-chip
            v-if="props.row.reminded_at"
            dense
            size="sm"
            color="green-2"
            text-color="green-10"
            :label="`Relancé le ${formatDate(props.row.reminded_at)}`"
          />
          <q-chip v-else dense size="sm" color="grey-3" text-color="grey-8" label="En attente" />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
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
