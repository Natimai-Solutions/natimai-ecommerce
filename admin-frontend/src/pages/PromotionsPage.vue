<template>
  <q-page class="admin-page">
    <PageHeader title="Promotions">
      <template #hint>
        Une promotion baisse automatiquement le prix d'un article ou de toute une catégorie, entre
        deux dates, pour tous les clients. Règle du <strong>meilleur prix</strong> : elle ne se
        cumule pas avec la remise ou le prix d'un groupe tarifaire — chaque client paie le plus bas
        des deux, et la boutique affiche son prix habituel barré.
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
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouvelle promotion"
          data-testid="promotion-create"
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
      data-testid="promotions"
    >
      <template #body-cell-name="props">
        <q-td :props="props">
          <div>{{ props.row.name }}</div>
          <div class="text-caption text-muted">{{ targetLabel(props.row) }}</div>
        </q-td>
      </template>
      <template #body-cell-value="props">
        <q-td :props="props" class="font-mono">{{ valueLabel(props.row) }}</q-td>
      </template>
      <template #body-cell-state="props">
        <q-td :props="props" align="center">
          <StatusTag
            :label="stateOf(props.row).label"
            :tone="stateOf(props.row).tone"
            :icon="toneIcon(stateOf(props.row).tone)"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn
            flat
            dense
            round
            icon="ph:pencil-simple"
            aria-label="Modifier"
            @click="openEdit(props.row)"
          >
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
          <q-toggle
            :model-value="props.row.is_active"
            dense
            color="positive"
            :disable="togglingId === props.row.id"
            @update:model-value="(val) => toggleActive(props.row, val)"
          >
            <q-tooltip>Active</q-tooltip>
          </q-toggle>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucune promotion.</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog" data-testid="promotion-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editing ? `Modifier « ${editing.name} »` : 'Nouvelle promotion' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="promotion-form">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              label="Nom (affiché au client) *"
              hint="Ex. : Rentrée −20 %"
              outlined
              dense
              maxlength="100"
              data-testid="promotion-name"
            />
            <q-option-group v-model="form.target" :options="targetOptions" inline dense />
            <q-select
              v-if="form.target === 'product'"
              v-model="form.product"
              :options="productOptions"
              label="Article *"
              outlined
              dense
              use-input
              input-debounce="300"
              clearable
              option-label="label"
              option-value="value"
              hint="Tapez un nom, un SKU ou une référence"
              data-testid="promotion-product"
              @filter="filterProducts"
            >
              <template #no-option>
                <q-item>
                  <q-item-section class="text-subtle">Aucun article trouvé</q-item-section>
                </q-item>
              </template>
            </q-select>
            <q-select
              v-else
              v-model="form.category_id"
              :options="categoryOptions"
              label="Catégorie *"
              outlined
              dense
              emit-value
              map-options
              data-testid="promotion-category"
            />
            <div class="promotion-form__row">
              <q-input
                v-model="form.percentage"
                label="Remise en %"
                type="number"
                step="any"
                min="0.01"
                max="100"
                outlined
                dense
                :disable="!!form.amount"
                data-testid="promotion-percentage"
              />
              <q-input
                v-model="form.amount"
                :label="`ou remise en montant (${currency})`"
                type="number"
                step="1"
                min="1"
                outlined
                dense
                :disable="!!form.percentage"
              />
            </div>
            <div class="promotion-form__row">
              <q-input v-model="form.start_date" label="Du" type="date" outlined dense />
              <q-input v-model="form.end_date" label="Au (inclus)" type="date" outlined dense />
            </div>
            <p class="text-caption text-muted q-mb-none">
              La remise porte sur le prix de référence (celui du groupe par défaut). Sans date de
              fin, la promotion dure jusqu'à ce que vous la désactiviez.
            </p>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="editing ? 'Enregistrer' : 'Créer la promotion'"
              :loading="saving"
              data-testid="promotion-save"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { intlLocale } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, type StatusTone } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
import {
  createDiscount,
  getProductName,
  listDiscounts,
  searchProducts,
  updateDiscount,
  type Discount,
  type DiscountCreate,
} from '@/api/discounts';
import { listCategories } from '@/api/categories';
import { extractApiError } from '@/api/errors';
import { useShopConfigStore } from '@/stores/shopConfig';

type PromotionTarget = 'product' | 'category';
interface Choice {
  label: string;
  value: string;
}

const shopConfig = useShopConfigStore();
const currency = computed(() => shopConfig.currency);
const rows = ref<Discount[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const togglingId = ref<string | null>(null);
const productNames = ref<Record<string, string>>({});
const categoryOptions = ref<Choice[]>([]);
const productOptions = ref<Choice[]>([]);

const targetOptions = [
  { label: 'Un article', value: 'product' },
  { label: 'Une catégorie', value: 'category' },
];

const columns: QTableColumn<Discount>[] = [
  { name: 'name', label: 'Promotion', field: 'name', align: 'left' },
  { name: 'value', label: 'Remise', field: 'percentage', align: 'left' },
  {
    name: 'validity',
    label: 'Période',
    field: (row) => `${fmtDate(row.start_date)} → ${fmtDate(row.end_date)}`,
    align: 'left',
  },
  { name: 'state', label: 'État', field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

function fmtDate(value: string | null): string {
  if (!value) return '∞';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(intlLocale());
}

function valueLabel(d: Discount): string {
  if (d.percentage) return `−${Number(d.percentage).toLocaleString(intlLocale())} %`;
  if (d.amount) return `−${Number(d.amount).toLocaleString(intlLocale())} ${currency.value}`;
  return '—';
}

function targetLabel(d: Discount): string {
  if (d.target === 'category') {
    const category = categoryOptions.value.find((c) => c.value === d.category_id);
    return `Catégorie ${category?.label ?? '—'}`;
  }
  return `Article ${d.product_id ? (productNames.value[d.product_id] ?? '…') : '—'}`;
}

function stateOf(d: Discount): { label: string; tone: StatusTone } {
  if (!d.is_active) return { label: 'Désactivée', tone: 'neutral' };
  const now = Date.now();
  if (d.start_date && new Date(d.start_date).getTime() > now)
    return { label: 'Programmée', tone: 'neutral' };
  if (d.end_date && new Date(d.end_date).getTime() < now)
    return { label: 'Terminée', tone: 'warn' };
  return { label: 'En cours', tone: 'ok' };
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (await listDiscounts()).filter((d) => d.discount_type === 'promotion');
    const missing = rows.value
      .map((d) => d.product_id)
      .filter((id): id is string => !!id && !(id in productNames.value));
    const names = await Promise.all(missing.map(async (id) => [id, await getProductName(id)]));
    productNames.value = {
      ...productNames.value,
      ...Object.fromEntries(names.map(([id, name]) => [id, name ?? 'introuvable'])),
    };
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function loadCategories() {
  try {
    categoryOptions.value = (await listCategories()).map((c) => ({ label: c.name, value: c.id }));
  } catch {
    // The selector stays empty; an article can still be targeted.
  }
}

function filterProducts(term: string, update: (fn: () => void) => void) {
  void (async () => {
    const found = term.trim().length >= 2 ? await searchProducts(term.trim()) : [];
    update(() => {
      productOptions.value = found.map((p) => ({
        value: p.id,
        label: p.supplier_sku ? `${p.name} (${p.supplier_sku})` : p.name,
      }));
    });
  })();
}

// --- Create / edit --------------------------------------------------------
const dialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editing = ref<Discount | null>(null);
const form = reactive<{
  name: string;
  target: PromotionTarget;
  product: Choice | null;
  category_id: string | null;
  percentage: string;
  amount: string;
  start_date: string;
  end_date: string;
}>({
  name: '',
  target: 'product',
  product: null,
  category_id: null,
  percentage: '',
  amount: '',
  start_date: '',
  end_date: '',
});

function resetForm(source?: Discount) {
  form.name = source?.name ?? '';
  form.target = source?.target === 'category' ? 'category' : 'product';
  form.product = source?.product_id
    ? { value: source.product_id, label: productNames.value[source.product_id] ?? '…' }
    : null;
  form.category_id = source?.category_id ?? null;
  form.percentage = source?.percentage ? String(Number(source.percentage)) : '';
  form.amount = source?.amount ? String(Number(source.amount)) : '';
  form.start_date = source?.start_date ? source.start_date.slice(0, 10) : '';
  form.end_date = source?.end_date ? source.end_date.slice(0, 10) : '';
}

function openCreate() {
  editing.value = null;
  dialogError.value = null;
  resetForm();
  dialog.value = true;
}

function openEdit(promotion: Discount) {
  editing.value = promotion;
  dialogError.value = null;
  resetForm(promotion);
  dialog.value = true;
}

function validate(): string | null {
  if (!form.name.trim()) return 'Donnez un nom à la promotion.';
  if (form.target === 'product' && !form.product) return 'Choisissez un article.';
  if (form.target === 'category' && !form.category_id) return 'Choisissez une catégorie.';
  if (!form.percentage && !form.amount) return 'Indiquez un pourcentage ou un montant.';
  if (form.start_date && form.end_date && form.end_date < form.start_date)
    return 'La date de fin précède la date de début.';
  return null;
}

function buildPayload(): DiscountCreate {
  return {
    name: form.name.trim(),
    description: null,
    discount_type: 'promotion',
    code: null,
    percentage: form.percentage || null,
    amount: form.amount || null,
    min_order_amount: null,
    max_uses: null,
    max_uses_per_customer: null,
    target: form.target,
    product_id: form.target === 'product' ? (form.product?.value ?? null) : null,
    category_id: form.target === 'category' ? form.category_id : null,
    start_date: form.start_date ? `${form.start_date}T00:00:00` : null,
    end_date: form.end_date ? `${form.end_date}T23:59:59` : null,
  };
}

async function submit() {
  dialogError.value = validate();
  if (dialogError.value) return;
  saving.value = true;
  try {
    const payload = buildPayload();
    if (form.product) productNames.value[form.product.value] = form.product.label;
    if (editing.value) await updateDiscount(editing.value.id, payload);
    else await createDiscount(payload);
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function toggleActive(promotion: Discount, value: boolean) {
  togglingId.value = promotion.id;
  error.value = null;
  try {
    await updateDiscount(promotion.id, { is_active: value });
    promotion.is_active = value;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Mise à jour impossible.';
  } finally {
    togglingId.value = null;
  }
}

onMounted(() => {
  void shopConfig.load();
  void loadCategories();
  void load();
});
</script>

<style scoped>
.promotion-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.promotion-form__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 10px;
}
</style>
