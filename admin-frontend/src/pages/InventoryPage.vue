<template>
  <q-page padding>
    <div class="text-h6 q-mb-sm">Inventaire</div>
    <div class="text-caption text-grey-7 q-mb-md">
      « Stock local » = unités physiquement à l'entrepôt (produits propres, ou unités achetées
      d'avance d'un produit fournisseur). « Dispo fournisseur » vient de la synchronisation et ne
      s'édite pas ici. Le checkout consomme le stock local en priorité, puis le fournisseur.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{
      notice
    }}</q-banner>

    <div class="row items-center q-gutter-sm q-mb-sm">
      <q-input
        v-model="search"
        outlined
        dense
        clearable
        debounce="400"
        label="Rechercher (nom, fournisseur)"
        class="col-12 col-sm-4"
        @update:model-value="onFilterChange"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-toggle v-model="onlyLocal" label="Avec stock local uniquement" @update:model-value="onFilterChange" />
      <q-space />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="product_id"
      flat
      bordered
      :loading="loading"
      v-model:pagination="pagination"
      :rows-per-page-options="[25, 50, 100]"
      @request="onRequest"
    >
      <template #body-cell-supplier="props">
        <q-td :props="props">
          <template v-if="props.row.is_supplier_managed">
            <q-chip dense size="sm" color="indigo-1" text-color="indigo-9" icon="sync">
              {{ props.row.supplier_name || 'Fournisseur' }}
            </q-chip>
            {{ formatQty(props.row.supplier_quantity) }}
          </template>
          <span v-else class="text-grey-5">—</span>
        </q-td>
      </template>
      <template #body-cell-local="props">
        <q-td :props="props">
          <span :class="Number(props.row.local_quantity) > 0 ? 'text-weight-bold' : 'text-grey-6'">
            {{ formatQty(props.row.local_quantity) }}
          </span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="tune"
            color="primary"
            label="Ajuster"
            @click="openAdjust(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun produit.</div>
      </template>
    </q-table>

    <!-- Adjust dialog -->
    <q-dialog v-model="adjustDialog">
      <q-card style="min-width: 420px">
        <q-card-section class="text-h6">Ajuster le stock local</q-card-section>
        <q-form @submit.prevent="submitAdjust">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <div class="text-body2 text-weight-medium">{{ adjustTarget?.product_name }}</div>
            <q-banner
              v-if="adjustTarget?.is_supplier_managed"
              dense
              rounded
              class="bg-blue-1 text-blue-10"
            >
              Produit synchronisé ({{ adjustTarget?.supplier_name || 'fournisseur' }}) : n'entrez
              ici que les unités réellement stockées à l'entrepôt — la dispo fournisseur est gérée
              par la synchronisation.
            </q-banner>
            <q-input
              v-model="adjustQuantity"
              label="Nouvelle quantité locale *"
              type="number"
              min="0"
              step="1"
              outlined
              dense
              autofocus
              :rules="[(v) => (v !== null && v !== '' && Number(v) >= 0) || 'Quantité ≥ 0 requise']"
            />
            <q-input
              v-model="adjustReason"
              label="Motif *"
              outlined
              dense
              :rules="[(v) => (!!v && v.trim().length >= 3) || 'Motif requis (min. 3 caractères)']"
              hint="Tracé dans les mouvements de stock (réception, casse, correction…)."
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { adjustInventory, listInventory, type InventoryItem } from '@/api/inventory';
import { extractApiError } from '@/api/errors';

const rows = ref<InventoryItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const search = ref<string | null>(null);
const onlyLocal = ref(false);
const pagination = ref({ page: 1, rowsPerPage: 50, rowsNumber: 0 });

const columns: QTableColumn[] = [
  { name: 'name', label: 'Produit', field: 'product_name', align: 'left' },
  { name: 'supplier', label: 'Dispo fournisseur (sync)', field: 'supplier_quantity', align: 'left' },
  { name: 'local', label: 'Stock local', field: 'local_quantity', align: 'left' },
  { name: 'actions', label: '', field: 'product_id', align: 'right' },
];

function formatQty(raw: string): string {
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? String(n) : raw;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const { page, rowsPerPage } = pagination.value;
    const res = await listInventory({
      search: search.value?.trim() || undefined,
      only_local: onlyLocal.value || undefined,
      skip: (page - 1) * rowsPerPage,
      limit: rowsPerPage,
    });
    rows.value = res.data;
    pagination.value.rowsNumber = res.count;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

function onFilterChange() {
  pagination.value.page = 1;
  void load();
}

function onRequest(props: { pagination: { page: number; rowsPerPage: number } }) {
  pagination.value.page = props.pagination.page;
  pagination.value.rowsPerPage = props.pagination.rowsPerPage;
  void load();
}

// --- Adjust ---
const adjustDialog = ref(false);
const adjustTarget = ref<InventoryItem | null>(null);
const adjustQuantity = ref<string>('0');
const adjustReason = ref('');
const saving = ref(false);
const dialogError = ref<string | null>(null);

function openAdjust(item: InventoryItem) {
  adjustTarget.value = item;
  adjustQuantity.value = formatQty(item.local_quantity);
  adjustReason.value = '';
  dialogError.value = null;
  adjustDialog.value = true;
}

async function submitAdjust() {
  if (!adjustTarget.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await adjustInventory({
      product_id: adjustTarget.value.product_id,
      place_id: adjustTarget.value.place_id,
      quantity: adjustQuantity.value,
      reason: adjustReason.value.trim(),
    });
    adjustDialog.value = false;
    notice.value = 'Stock ajusté.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Ajustement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
