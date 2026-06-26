<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Commandes fournisseurs</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="row q-col-gutter-md q-mb-md items-end">
      <q-select
        v-model="statusFilter"
        :options="statusOptions"
        label="Statut"
        outlined
        dense
        emit-value
        map-options
        clearable
        class="col-12 col-sm-3"
        @update:model-value="load"
      />
      <q-input
        v-model="supplierFilter"
        label="Fournisseur (ex: ingram_micro)"
        outlined
        dense
        clearable
        class="col-12 col-sm-4"
        @update:model-value="load"
      />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-blue-1 text-blue-10 q-mb-md" dense rounded>{{ notice }}</q-banner>

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
          <q-chip dense :color="statusColor(props.row.status)" text-color="white" :label="props.row.status" />
        </q-td>
      </template>
      <template #body-cell-customer_order_number="props">
        <q-td :props="props">
          <span :title="props.row.customer_order_number">{{ props.row.customer_order_number.slice(0, 8) }}</span>
        </q-td>
      </template>
      <template #body-cell-error_message="props">
        <q-td :props="props">
          <span v-if="props.row.error_message" class="text-negative">{{ props.row.error_message }}</span>
          <span v-else class="text-grey-5">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            icon="replay"
            color="primary"
            label="Réessayer"
            no-caps
            :loading="retryingId === props.row.id"
            :disable="props.row.status === 'submitted'"
            @click="onRetry(props.row)"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import {
  listSupplierOrders,
  retrySupplierOrder,
  type SupplierOrder,
  type SupplierOrderStatus,
} from 'src/api/supplierOrders'
import { extractApiError } from 'src/api/errors'

const rows = ref<SupplierOrder[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const statusFilter = ref<SupplierOrderStatus | null>(null)
const supplierFilter = ref<string | null>(null)
const retryingId = ref<string | null>(null)

const statusOptions = [
  { label: 'En attente', value: 'pending' },
  { label: 'Soumise', value: 'submitted' },
  { label: 'Erreur', value: 'error' },
  { label: 'Ignorée', value: 'skipped' },
]

const columns: QTableColumn[] = [
  { name: 'created_at', label: 'Créée', field: 'created_at', align: 'left' },
  { name: 'supplier_name', label: 'Fournisseur', field: 'supplier_name', align: 'left' },
  { name: 'customer_order_number', label: 'Réf. commande', field: 'customer_order_number', align: 'left' },
  { name: 'supplier_order_number', label: 'N° PO', field: (r) => r.supplier_order_number ?? '—', align: 'left' },
  { name: 'status', label: 'Statut', field: 'status', align: 'left' },
  { name: 'attempts', label: 'Tentatives', field: 'attempts', align: 'center' },
  { name: 'error_message', label: 'Erreur', field: 'error_message', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

function statusColor(status: SupplierOrderStatus): string {
  if (status === 'submitted') return 'green'
  if (status === 'error') return 'negative'
  if (status === 'pending') return 'orange'
  return 'blue-grey'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params: { status?: SupplierOrderStatus; supplier_name?: string } = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (supplierFilter.value) params.supplier_name = supplierFilter.value
    const res = await listSupplierOrders(params)
    rows.value = res.data
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

async function onRetry(order: SupplierOrder) {
  retryingId.value = order.id
  notice.value = null
  error.value = null
  try {
    const updated = await retrySupplierOrder(order.id)
    const idx = rows.value.findIndex((r) => r.id === updated.id)
    if (idx !== -1) rows.value[idx] = updated
    notice.value =
      updated.status === 'submitted'
        ? `PO soumis (n° ${updated.supplier_order_number ?? '—'}).`
        : `Nouvelle tentative : statut « ${updated.status} »${updated.error_message ? ` — ${updated.error_message}` : ''}.`
  } catch (err) {
    error.value = extractApiError(err) ?? 'Échec de la nouvelle tentative.'
  } finally {
    retryingId.value = null
  }
}

onMounted(load)
</script>
