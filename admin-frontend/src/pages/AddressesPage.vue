<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('addresses.title')" :hint="$t('addresses.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('addresses.refresh')"
          :loading="loading"
          @click="reload"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-select
        v-model="filter"
        :options="filterOptions"
        :label="$t('addresses.status_filter')"
        outlined
        dense
        emit-value
        map-options
        style="min-width: 220px"
        @update:model-value="reload"
      />
    </div>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

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
          <div class="text-caption text-muted">
            {{
              [
                `${props.row.postal_code} ${props.row.city}`.trim(),
                props.row.state,
                countryLabel(props.row.country),
              ]
                .filter((p) => !!p && String(p).trim().length > 0)
                .join(', ')
            }}
          </div>
        </q-td>
      </template>

      <template #body-cell-validated="props">
        <q-td :props="props" align="center">
          <StatusTag
            :tone="props.row.is_validated ? 'ok' : 'neutral'"
            :icon="props.row.is_validated ? 'ph:seal-check' : 'ph:clock'"
            :label="
              props.row.is_validated ? $t('addresses.validated') : $t('addresses.not_validated')
            "
          />
        </q-td>
      </template>

      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="!props.row.is_validated"
            flat
            dense
            no-caps
            icon="ph:check"
            :label="$t('addresses.validate')"
            :loading="validatingIds.has(props.row.id)"
            @click="onValidate(props.row)"
          />
        </q-td>
      </template>

      <template #no-data>
        <span class="text-subtle">{{
          loading ? $t('addresses.loading') : $t('addresses.none')
        }}</span>
      </template>
    </q-table>

    <div class="text-caption text-muted q-mt-sm">{{ $t('addresses.count', { n: count }) }}</div>
  </q-page>
</template>

<script setup lang="ts">
import { extractApiError } from '@/api/errors';
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { countryLabel } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { listAddresses, validateAddress, type AdminAddress } from '@/api/addresses';

const { t } = useI18n();

type Filter = 'all' | 'pending' | 'validated';

const rows = ref<AdminAddress[]>([]);
const count = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const filter = ref<Filter>('pending');
const validatingIds = ref<Set<string>>(new Set());

const filterOptions = computed(() => [
  { label: t('addresses.f_pending'), value: 'pending' as const },
  { label: t('addresses.f_validated'), value: 'validated' as const },
  { label: t('addresses.f_all'), value: 'all' as const },
]);

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'email',
    label: t('addresses.col_customer'),
    field: (row) => row.user_email || row.user_id,
    align: 'left',
  },
  { name: 'address', label: t('addresses.col_address'), field: 'street', align: 'left' },
  { name: 'type', label: t('addresses.col_type'), field: 'type', align: 'left' },
  {
    name: 'validated',
    label: t('addresses.col_validation'),
    field: 'is_validated',
    align: 'center',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function reload() {
  loading.value = true;
  error.value = null;
  try {
    const validated = filter.value === 'all' ? null : filter.value === 'validated';
    const data = await listAddresses({ validated, limit: 500 });
    rows.value = data.data;
    count.value = data.count;
  } catch (err: unknown) {
    error.value = extractApiError(err) ?? t('addresses.load_failed');
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
    error.value = extractApiError(err) ?? t('addresses.validate_failed');
  } finally {
    validatingIds.value.delete(address.id);
    validatingIds.value = new Set(validatingIds.value);
  }
}

onMounted(() => {
  void reload();
});
</script>
