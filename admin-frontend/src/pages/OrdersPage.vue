<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Commandes clients</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="loading" class="text-center q-pa-lg">
      <q-spinner color="primary" size="2em" />
    </div>

    <q-banner v-else-if="rows.length === 0" class="bg-blue-1 text-blue-10" rounded>
      <template #avatar><q-icon name="info" /></template>
      Aucune commande.
    </q-banner>

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
          <span :title="props.row.order_id">#{{ props.row.order_id.slice(0, 8) }}</span>
        </q-td>
      </template>
      <template #body-cell-client="props">
        <q-td :props="props">
          <div>
            {{ props.row.user_name || props.row.user_email || props.row.user_id.slice(0, 8) }}
          </div>
          <div
            v-if="props.row.user_name && props.row.user_email"
            class="text-caption text-grey-6"
          >
            {{ props.row.user_email }}
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="orderStatusColor(props.row.status)"
            text-color="white"
            :label="orderStatusLabel(props.row.status)"
          />
        </q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props" class="text-weight-medium">
          {{ formatMoney(props.row.total_amount) }}
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="visibility"
            color="primary"
            label="Détail"
            :to="`/orders/${props.row.order_id}`"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import { formatXpf } from '@app/utils'
import {
  listOrders,
  orderStatusColor,
  orderStatusLabel,
  type AdminOrderListItem,
} from 'src/api/orders'
import { extractApiError } from 'src/api/errors'

const rows = ref<AdminOrderListItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

function formatMoney(amount: number): string {
  return Number.isFinite(amount) ? formatXpf(amount) : String(amount)
}

function formatDate(raw: string | null): string {
  if (!raw) return '—'
  const d = new Date(raw)
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
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
  { name: 'total', label: 'Total', field: 'total_amount', align: 'left' },
  { name: 'actions', label: '', field: 'order_id', align: 'right' },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    rows.value = await listOrders()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
