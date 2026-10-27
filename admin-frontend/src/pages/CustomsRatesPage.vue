<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('customs.title')">
      <template #hint>
        {{ $t('customs.hint') }}
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

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="report" class="customs-kpis">
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">{{ $t('customs.kpi_publishable') }}</span>
        <span class="customs-kpi__value font-mono"
          >{{ report.publishable_count }} / {{ report.enriched_count }}</span
        >
        <span class="customs-kpi__hint">{{ $t('customs.kpi_publishable_hint') }}</span>
      </div>
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">{{ $t('customs.kpi_no_rate') }}</span>
        <span
          class="customs-kpi__value font-mono"
          :class="report.blocked_customs_rate_unresolved ? 'text-negative' : 'text-positive'"
        >
          {{ report.blocked_customs_rate_unresolved }}
        </span>
        <span class="customs-kpi__hint">{{ $t('customs.kpi_no_rate_hint') }}</span>
      </div>
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">{{ $t('customs.kpi_no_weight') }}</span>
        <span
          class="customs-kpi__value font-mono"
          :class="report.blocked_weight_missing ? 'text-negative' : 'text-positive'"
        >
          {{ report.blocked_weight_missing }}
        </span>
        <span class="customs-kpi__hint">{{ $t('customs.kpi_no_weight_hint') }}</span>
      </div>
    </div>

    <q-table
      :rows="tableRows"
      :columns="columns"
      row-key="category_id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-category_name="props">
        <q-td :props="props">
          <span v-if="props.row.category_name">{{ props.row.category_name }}</span>
          <span v-else class="text-subtle text-italic">{{ $t('customs.no_category') }}</span>
        </q-td>
      </template>
      <template #body-cell-rate="props">
        <q-td :props="props">
          <span
            v-if="!props.row.default_customs_rate_pct && props.row.inherited_rate"
            class="font-mono text-muted"
            >{{ props.row.inherited_rate }} %
            <span class="text-caption">{{
              $t('customs.inherited_from', { name: props.row.inherited_from })
            }}</span></span
          >
          <span v-else-if="props.row.default_customs_rate_pct" class="font-mono"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <StatusTag
            v-else
            :label="$t('customs.undefined')"
            tone="danger"
            icon="ph:warning-circle"
          />
        </q-td>
      </template>
      <template #body-cell-product_count="props">
        <q-td :props="props" class="font-mono">{{ props.row.product_count }}</q-td>
      </template>
      <template #body-cell-blocked="props">
        <q-td :props="props">
          <StatusTag
            :label="String(props.row.blocked_count)"
            :tone="props.row.blocked_count ? 'danger' : 'ok'"
            :icon="props.row.blocked_count ? 'ph:eye-slash' : 'ph:check-circle'"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="props.row.category_id"
            flat
            round
            dense
            icon="ph:pencil-simple"
            @click="openEdit(props.row)"
          >
            <q-tooltip>{{ $t('customs.set_rate') }}</q-tooltip>
          </q-btn>
          <q-tooltip v-else>
            {{ $t('customs.no_category_hint') }}
          </q-tooltip>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('customs.none') }}</div>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ editing?.category_name ?? $t('customs.category') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="editRate"
              :label="$t('customs.rate')"
              :hint="$t('customs.rate_hint')"
              type="number"
              step="0.01"
              outlined
              dense
            />
            <p class="admin-hint q-mb-none">
              <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
              <span v-html="$t('customs.help')"></span>
            </p>
            <AppNotice tone="warning" dense>
              <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
              <span v-html="$t('customs.vat_warning')"></span>
            </AppNotice>
            <p class="admin-hint q-mb-none">
              <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
              <span v-html="$t('customs.procedure')"></span>
            </p>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              type="submit"
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
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  getPublicationReport,
  setCategoryCustomsRate,
  type CategoryPublicationRow,
  type PublicationReport,
} from '@/api/taxRates';
import { listAdminCategories, type AdminCategory } from '@/api/categories';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const report = ref<PublicationReport | null>(null);
/** Every live category, products or not: a rate is set before the products arrive. */
const categories = ref<AdminCategory[]>([]);

type CustomsRow = CategoryPublicationRow & {
  /** Rate in force when the category sets none: an ancestor's. */
  inherited_rate?: string | null;
  inherited_from?: string | null;
};

// One row per live category (tree order, full path), with the report's
// counts; the report's « sans catégorie » row stays at the end.
const tableRows = computed<CustomsRow[]>(() => {
  const counts = new Map(
    (report.value?.categories ?? [])
      .filter((r) => r.category_id)
      .map((r) => [r.category_id as string, r]),
  );
  const rows: CustomsRow[] = categories.value
    .filter((c) => c.is_active && !c.merged_into_id)
    .map((c) => {
      const counted = counts.get(c.id);
      return {
        category_id: c.id,
        category_name: c.path.join(' › '),
        default_customs_rate_pct: c.default_customs_rate_pct,
        default_tax_rate_id: c.default_tax_rate_id,
        product_count: counted?.product_count ?? 0,
        blocked_count: counted?.blocked_count ?? 0,
        inherited_rate: c.default_customs_rate_pct ? null : c.inherited_customs_rate_pct,
        inherited_from: c.inherited_customs_rate_from,
      };
    });
  for (const row of report.value?.categories ?? []) {
    if (!row.category_id) rows.push(row);
  }
  return rows;
});
const loading = ref(false);
const error = ref<string | null>(null);

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'category_name',
    label: t('customs.col_category'),
    field: 'category_name',
    align: 'left',
  },
  { name: 'rate', label: t('customs.col_rate'), field: 'default_customs_rate_pct', align: 'left' },
  {
    name: 'product_count',
    label: t('customs.col_products'),
    field: 'product_count',
    align: 'right',
  },
  { name: 'blocked', label: t('customs.col_hidden'), field: 'blocked_count', align: 'left' },
  { name: 'actions', label: '', field: 'category_id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [report.value, categories.value] = await Promise.all([
      getPublicationReport(),
      listAdminCategories(),
    ]);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

const editDialog = ref(false);
const editing = ref<CategoryPublicationRow | null>(null);
const editRate = ref('');
const saving = ref(false);
const dialogError = ref<string | null>(null);

function openEdit(row: CategoryPublicationRow) {
  dialogError.value = null;
  editing.value = row;
  editRate.value = row.default_customs_rate_pct ?? '';
  editDialog.value = true;
}

async function submitEdit() {
  const categoryId = editing.value?.category_id;
  if (!categoryId) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await setCategoryCustomsRate(categoryId, editRate.value.trim() || null);
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.customs-kpis {
  margin-bottom: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.customs-kpi {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.customs-kpi__label,
.customs-kpi__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}

.customs-kpi__value {
  font-size: 24px;
  font-weight: 500;
  line-height: 1.2;
}
</style>
