<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('inventory.title')">
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
    <p class="admin-hint">
      {{ $t('inventory.intro') }}
    </p>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div class="admin-toolbar">
      <q-input
        v-model="search"
        outlined
        dense
        clearable
        debounce="400"
        :label="$t('inventory.search')"
        style="min-width: 280px"
        @update:model-value="onFilterChange"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-toggle
        v-model="onlyLocal"
        :label="$t('inventory.local_only')"
        @update:model-value="onFilterChange"
      />
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
            <q-chip dense size="sm" icon="ph:arrows-clockwise">
              {{ props.row.supplier_name || $t('inventory.supplier') }}
            </q-chip>
            <span class="font-mono">{{ formatQty(props.row.supplier_quantity) }}</span>
          </template>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-local="props">
        <q-td :props="props">
          <span
            class="font-mono"
            :class="Number(props.row.local_quantity) > 0 ? 'text-weight-bold' : 'text-subtle'"
          >
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
            icon="ph:sliders-horizontal"
            :label="$t('inventory.adjust')"
            @click="openAdjust(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('inventory.none') }}</div>
      </template>
    </q-table>

    <!-- Adjust dialog -->
    <q-dialog v-model="adjustDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('inventory.adjust_title') }}</h2>
          <p class="app-dialog__text">{{ adjustTarget?.product_name }}</p>
        </q-card-section>
        <q-form @submit.prevent="submitAdjust">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <AppNotice v-if="adjustTarget?.is_supplier_managed" tone="info" dense>
              {{
                $t('inventory.synced_notice', {
                  supplier: adjustTarget?.supplier_name || $t('inventory.supplier'),
                })
              }}
            </AppNotice>
            <q-input
              v-model="adjustQuantity"
              :label="$t('inventory.new_qty')"
              type="number"
              min="0"
              step="1"
              outlined
              dense
              autofocus
              :rules="[
                (v) => (v !== null && v !== '' && Number(v) >= 0) || $t('inventory.qty_rule'),
              ]"
            />
            <q-input
              v-model="adjustReason"
              :label="$t('inventory.reason')"
              outlined
              dense
              :rules="[(v) => (!!v && v.trim().length >= 3) || $t('inventory.reason_rule')]"
              :hint="$t('inventory.reason_hint')"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import PageHeader from '@/components/PageHeader.vue';
import { adjustInventory, listInventory, type InventoryItem } from '@/api/inventory';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const rows = ref<InventoryItem[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const search = ref<string | null>(null);
const onlyLocal = ref(false);
const pagination = ref({ page: 1, rowsPerPage: 50, rowsNumber: 0 });

const columns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('inventory.col_product'), field: 'product_name', align: 'left' },
  {
    name: 'supplier',
    label: t('inventory.col_supplier'),
    field: 'supplier_quantity',
    align: 'left',
  },
  { name: 'local', label: t('inventory.col_local'), field: 'local_quantity', align: 'left' },
  { name: 'actions', label: '', field: 'product_id', align: 'right' },
]);

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
    error.value = extractApiError(err) ?? t('common.load_failed');
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
    notice.value = t('inventory.adjusted');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('inventory.adjust_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
