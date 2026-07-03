<template>
  <q-page padding>
    <div class="row q-col-gutter-md q-mb-md items-end">
      <div class="col-12 col-md-4">
        <q-select
          v-model="filter"
          :options="filterOptions"
          label="Statut de validation"
          outlined
          dense
          emit-value
          map-options
          @update:model-value="reload"
        />
      </div>
      <div class="col-12 col-md-8 text-right">
        <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="reload" />
      </div>
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

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
      <template #body-cell-address="props">
        <q-td :props="props">
          <div class="text-body2">{{ props.row.street }}</div>
          <div class="text-caption text-grey-7">
            {{ [`${props.row.postal_code} ${props.row.city}`.trim(), props.row.state, props.row.country]
              .filter((p) => !!p && String(p).trim().length > 0)
              .join(', ') }}
          </div>
        </q-td>
      </template>

      <template #body-cell-validated="props">
        <q-td :props="props" align="center">
          <q-chip
            :color="props.row.is_validated ? 'positive' : 'grey-5'"
            text-color="white"
            :icon="props.row.is_validated ? 'verified' : 'schedule'"
            :label="props.row.is_validated ? 'Validée' : 'Non validée'"
            dense
          />
        </q-td>
      </template>

      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="!props.row.is_validated"
            unelevated
            color="positive"
            icon="check"
            label="Valider"
            dense
            :loading="validatingIds.has(props.row.id)"
            @click="onValidate(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <div class="text-caption text-grey-7 q-mt-sm">{{ count }} adresse(s)</div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { listAddresses, validateAddress, type AdminAddress } from 'src/api/addresses';

type Filter = 'all' | 'pending' | 'validated';

const rows = ref<AdminAddress[]>([]);
const count = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const filter = ref<Filter>('pending');
const validatingIds = ref<Set<string>>(new Set());

const filterOptions = [
  { label: 'Non validées', value: 'pending' as const },
  { label: 'Validées', value: 'validated' as const },
  { label: 'Toutes', value: 'all' as const },
];

const columns: QTableColumn[] = [
  { name: 'email', label: 'Client', field: (row) => row.user_email || row.user_id, align: 'left' },
  { name: 'address', label: 'Adresse', field: 'street', align: 'left' },
  { name: 'type', label: 'Type', field: 'type', align: 'left' },
  { name: 'validated', label: 'Validation', field: 'is_validated', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function reload() {
  loading.value = true;
  error.value = null;
  try {
    const validated = filter.value === 'all' ? null : filter.value === 'validated';
    const data = await listAddresses({ validated, limit: 500 });
    rows.value = data.data;
    count.value = data.count;
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Erreur de chargement';
  } finally {
    loading.value = false;
  }
}

async function onValidate(address: AdminAddress) {
  validatingIds.value.add(address.id);
  validatingIds.value = new Set(validatingIds.value);
  try {
    await validateAddress(address.id);
    // Reflect the change without a full reload; drop from the "pending" view.
    if (filter.value === 'pending') {
      rows.value = rows.value.filter((a) => a.id !== address.id);
      count.value = Math.max(0, count.value - 1);
    } else {
      address.is_validated = true;
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Échec de la validation';
  } finally {
    validatingIds.value.delete(address.id);
    validatingIds.value = new Set(validatingIds.value);
  }
}

onMounted(() => {
  void reload();
});
</script>
