<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('discounts.title')">
      <template #hint>
        {{ $t('discounts.intro') }}
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
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('discounts.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

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
      <template #body-cell-code="props">
        <q-td :props="props">
          <span class="font-mono text-weight-medium">{{ props.row.code ?? '—' }}</span>
          <div class="text-caption text-muted">{{ props.row.name }}</div>
        </q-td>
      </template>
      <template #body-cell-value="props">
        <q-td :props="props">{{ valueLabel(props.row) }}</q-td>
      </template>
      <template #body-cell-uses="props">
        <q-td :props="props" align="center">
          <span class="font-mono"
            >{{ props.row.current_uses
            }}<span v-if="props.row.max_uses"> / {{ props.row.max_uses }}</span></span
          >
          <div v-if="props.row.max_uses_per_customer" class="text-caption text-muted">
            {{ $t('discounts.per_customer', { n: props.row.max_uses_per_customer }) }}
          </div>
        </q-td>
      </template>
      <template #body-cell-state="props">
        <q-td :props="props" align="center">
          <StatusTag
            :label="stateOf(props.row).label"
            :tone="toneOf(stateOf(props.row).color)"
            :icon="toneIcon(toneOf(stateOf(props.row).color))"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn flat dense round icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-toggle
            :model-value="props.row.is_active"
            dense
            color="positive"
            :disable="togglingId === props.row.id"
            @update:model-value="(val) => toggleActive(props.row, val)"
          >
            <q-tooltip>{{ $t('discounts.active') }}</q-tooltip>
          </q-toggle>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('discounts.none') }}</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{
              editing
                ? $t('discounts.edit_title', { name: editing.code ?? editing.name })
                : $t('discounts.new_title')
            }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              :label="$t('discounts.name')"
              outlined
              dense
              :rules="req"
            />
            <q-input
              v-model="form.code"
              :label="$t('discounts.code')"
              :hint="$t('discounts.code_hint')"
              outlined
              dense
              :rules="req"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.percentage"
                :label="$t('discounts.percent')"
                type="number"
                step="0.01"
                min="0.01"
                max="100"
                outlined
                dense
                class="col-6"
                :disable="!!form.amount"
              />
              <q-input
                v-model="form.amount"
                :label="$t('discounts.amount', { currency })"
                type="number"
                step="1"
                min="1"
                outlined
                dense
                class="col-6"
                :disable="!!form.percentage"
              />
            </div>
            <q-select
              v-model="form.target"
              :options="targetOptions"
              :label="$t('discounts.applies')"
              outlined
              dense
              emit-value
              map-options
            />
            <q-input
              v-if="form.target === 'product'"
              v-model="form.product_id"
              :label="$t('discounts.product_id')"
              outlined
              dense
              :rules="req"
            />
            <q-select
              v-if="form.target === 'category'"
              v-model="form.category_id"
              :options="categoryOptions"
              :label="$t('discounts.category')"
              outlined
              dense
              emit-value
              map-options
              :rules="req"
            />
            <q-input
              v-model="form.min_order_amount"
              :label="$t('discounts.minimum', { currency })"
              type="number"
              min="0"
              outlined
              dense
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.max_uses"
                :label="$t('discounts.max_uses')"
                type="number"
                min="1"
                outlined
                dense
                class="col-6"
              />
              <q-input
                v-model.number="form.max_uses_per_customer"
                :label="$t('discounts.max_per_customer')"
                type="number"
                min="1"
                outlined
                dense
                class="col-6"
              />
            </div>
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.start_date"
                :label="$t('discounts.valid_from')"
                type="date"
                outlined
                dense
                class="col-6"
              />
              <q-input
                v-model="form.end_date"
                label="au"
                type="date"
                outlined
                dense
                class="col-6"
              />
            </div>
            <q-toggle
              v-model="form.applies_to_promoted"
              :label="$t('discounts.promoted')"
              data-testid="coupon-applies-to-promoted"
            />
            <div class="text-caption text-muted">
              {{ $t('discounts.promoted_off') }}
            </div>
            <q-input v-model="form.description" :label="$t('discounts.internal')" outlined dense />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="editing ? $t('discounts.save') : $t('discounts.create')"
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
import { intlLocale } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
import {
  DISCOUNT_TARGET_LABELS,
  createDiscount,
  listDiscounts,
  updateDiscount,
  type Discount,
  type DiscountCreate,
  type DiscountTarget,
} from '@/api/discounts';
import { listCategories, type Category } from '@/api/categories';
import { extractApiError } from '@/api/errors';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();

const shopConfig = useShopConfigStore();
const currency = computed(() => shopConfig.currency);
const rows = ref<Discount[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const togglingId = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).trim().length > 0) || t('common.required'),
];

const targetOptions = (Object.keys(DISCOUNT_TARGET_LABELS) as DiscountTarget[]).map((value) => ({
  value,
  label: DISCOUNT_TARGET_LABELS[value],
}));
const categoryOptions = ref<{ label: string; value: string }[]>([]);

function valueLabel(d: Discount): string {
  const base = d.percentage
    ? `-${Number(d.percentage)} %`
    : d.amount
      ? `-${Number(d.amount).toLocaleString(intlLocale())} ${currency.value}`
      : '—';
  const scope = DISCOUNT_TARGET_LABELS[d.target] ?? d.target;
  const min = d.min_order_amount
    ? t('discounts.from_amount', {
        amount: `${Number(d.min_order_amount).toLocaleString(intlLocale())} ${currency.value}`,
      })
    : '';
  const stack = d.applies_to_promoted === false ? t('discounts.not_promoted') : '';
  return `${base} · ${scope}${min}${stack}`;
}

function stateOf(d: Discount): { label: string; color: string } {
  if (!d.is_active) return { label: t('discounts.st_disabled'), color: 'grey-6' };
  const now = Date.now();
  if (d.start_date && new Date(d.start_date).getTime() > now)
    return { label: t('discounts.st_upcoming'), color: 'blue-6' };
  if (d.end_date && new Date(d.end_date).getTime() < now)
    return { label: t('discounts.st_expired'), color: 'orange-8' };
  if (d.max_uses !== null && d.current_uses >= d.max_uses)
    return { label: t('discounts.st_exhausted'), color: 'orange-8' };
  return { label: t('discounts.st_active'), color: 'positive' };
}

const columns = computed<QTableColumn<Discount>[]>(() => [
  { name: 'code', label: t('discounts.col_code'), field: 'code', align: 'left', sortable: true },
  { name: 'value', label: t('discounts.col_discount'), field: 'percentage', align: 'left' },
  { name: 'uses', label: t('discounts.col_uses'), field: 'current_uses', align: 'center' },
  {
    name: 'validity',
    label: t('discounts.col_validity'),
    field: (row) => `${fmtDate(row.start_date)} → ${fmtDate(row.end_date)}`,
    align: 'left',
  },
  { name: 'state', label: t('discounts.col_state'), field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

function fmtDate(value: string | null): string {
  if (!value) return '∞';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(intlLocale());
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (await listDiscounts()).filter((d) => d.discount_type === 'coupon');
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  try {
    const categories: Category[] = await listCategories();
    categoryOptions.value = categories.map((c) => ({ label: c.name, value: c.id }));
  } catch {
    // The selector stays empty; the target can still be set by product or order.
  }
}

// --- Create / edit --------------------------------------------------------
const dialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editing = ref<Discount | null>(null);
const form = reactive<{
  name: string;
  code: string;
  percentage: string;
  amount: string;
  target: DiscountTarget;
  product_id: string;
  category_id: string;
  min_order_amount: string;
  max_uses: number | null;
  max_uses_per_customer: number | null;
  start_date: string;
  end_date: string;
  description: string;
  applies_to_promoted: boolean;
}>({
  name: '',
  code: '',
  percentage: '',
  amount: '',
  target: 'order',
  product_id: '',
  category_id: '',
  min_order_amount: '',
  max_uses: null,
  max_uses_per_customer: null,
  start_date: '',
  end_date: '',
  description: '',
  applies_to_promoted: true,
});

function resetForm(source?: Discount) {
  form.name = source?.name ?? '';
  form.code = source?.code ?? '';
  form.percentage = source?.percentage ? String(Number(source.percentage)) : '';
  form.amount = source?.amount ? String(Number(source.amount)) : '';
  form.target = source?.target ?? 'order';
  form.product_id = source?.product_id ?? '';
  form.category_id = source?.category_id ?? '';
  form.min_order_amount = source?.min_order_amount ? String(Number(source.min_order_amount)) : '';
  form.max_uses = source?.max_uses ?? null;
  form.max_uses_per_customer = source?.max_uses_per_customer ?? null;
  form.start_date = source?.start_date ? source.start_date.slice(0, 10) : '';
  form.end_date = source?.end_date ? source.end_date.slice(0, 10) : '';
  form.description = source?.description ?? '';
  form.applies_to_promoted = source?.applies_to_promoted ?? true;
}

function openCreate() {
  editing.value = null;
  dialogError.value = null;
  resetForm();
  dialog.value = true;
}

function openEdit(discount: Discount) {
  editing.value = discount;
  dialogError.value = null;
  resetForm(discount);
  dialog.value = true;
}

function buildPayload(): DiscountCreate {
  return {
    name: form.name.trim(),
    description: form.description.trim() || null,
    discount_type: 'coupon',
    code: form.code.trim().toUpperCase(),
    percentage: form.percentage ? form.percentage : null,
    amount: form.amount ? form.amount : null,
    min_order_amount: form.min_order_amount ? form.min_order_amount : null,
    max_uses: form.max_uses || null,
    max_uses_per_customer: form.max_uses_per_customer || null,
    target: form.target,
    product_id: form.target === 'product' ? form.product_id.trim() || null : null,
    category_id: form.target === 'category' ? form.category_id || null : null,
    start_date: form.start_date ? `${form.start_date}T00:00:00` : null,
    end_date: form.end_date ? `${form.end_date}T23:59:59` : null,
    applies_to_promoted: form.applies_to_promoted,
  };
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  if (!form.percentage && !form.amount) {
    dialogError.value = t('discounts.err_value');
    saving.value = false;
    return;
  }
  try {
    const payload = buildPayload();
    if (editing.value) await updateDiscount(editing.value.id, payload);
    else await createDiscount(payload);
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function toggleActive(discount: Discount, value: boolean) {
  togglingId.value = discount.id;
  error.value = null;
  try {
    await updateDiscount(discount.id, { is_active: value });
    discount.is_active = value;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    togglingId.value = null;
  }
}

onMounted(() => {
  void shopConfig.load();
  void load();
  void loadCategories();
});
</script>
