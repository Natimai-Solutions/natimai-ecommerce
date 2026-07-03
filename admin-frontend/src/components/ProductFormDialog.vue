<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card style="min-width: 640px; max-width: 90vw">
      <q-card-section class="row items-center q-pb-none">
        <div class="text-h6">{{ isEdit ? 'Modifier le produit' : 'Nouveau produit' }}</div>
        <q-space />
        <q-badge v-if="isEdit && product?.is_supplier_managed" color="orange" label="Fournisseur" />
        <q-badge v-else-if="isEdit" color="teal" label="Manuel" />
      </q-card-section>

      <q-card-section>
        <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

        <q-banner
          v-if="isEdit && product?.is_supplier_managed"
          class="bg-blue-1 text-grey-8 q-mb-md"
          dense
        >
          Produit synchronisé depuis un fournisseur. Les champs que vous modifiez ici seront
          <strong>verrouillés</strong> et ne seront plus écrasés par la synchronisation.
        </q-banner>

        <q-form @submit="onSubmit">
          <q-input v-model="form.name" label="Nom *" outlined dense bottom-slots :rules="req" />
          <q-input
            v-model="form.description"
            label="Description courte"
            outlined
            dense
            bottom-slots
          />
          <q-input
            v-model="form.long_description"
            label="Description longue"
            type="textarea"
            autogrow
            outlined
            dense
            bottom-slots
          />

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Prix &amp; taxes</div>
          <div class="row" style="gap: 8px">
            <q-input
              v-model="form.cost_amount"
              label="Coût"
              type="number"
              step="0.01"
              outlined
              dense
              bottom-slots
              class="col"
            />
            <q-select
              v-model="form.cost_currency"
              :options="currencyOptions"
              label="Devise du coût"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              class="col"
            />
          </div>
          <div class="row" style="gap: 8px">
            <q-input
              v-model="form.customs_rate_pct"
              label="Douane (%)"
              type="number"
              step="0.01"
              outlined
              dense
              bottom-slots
              class="col"
            />
            <q-input
              v-model="form.base_price"
              label="Prix de base (0 = calculé)"
              type="number"
              step="0.01"
              outlined
              dense
              bottom-slots
              class="col"
            />
          </div>
          <div class="row" style="gap: 8px">
            <q-select
              v-model="form.category_id"
              :options="categoryOptions"
              label="Catégorie"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              clearable
              class="col"
            />
            <q-select
              v-model="form.tax_rate_id"
              :options="taxRateOptions"
              label="Taux de TVA / TGC"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              clearable
              class="col"
            />
          </div>

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Logistique</div>
          <q-select
            v-model="form.supplier_place_id"
            :options="placeOptions"
            label="Origine (fournisseur)"
            outlined
            dense
            bottom-slots
            emit-value
            map-options
            clearable
          />
          <div class="row" style="gap: 8px">
            <q-input
              v-model.number="form.weight"
              label="Poids (kg)"
              type="number"
              step="0.001"
              outlined
              dense
              bottom-slots
              class="col"
            />
            <q-input
              v-model.number="form.dimensions_length"
              label="Long. (cm)"
              type="number"
              outlined
              dense
              bottom-slots
              class="col"
            />
            <q-input
              v-model.number="form.dimensions_width"
              label="Larg. (cm)"
              type="number"
              outlined
              dense
              bottom-slots
              class="col"
            />
            <q-input
              v-model.number="form.dimensions_height"
              label="Haut. (cm)"
              type="number"
              outlined
              dense
              bottom-slots
              class="col"
            />
          </div>

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Affichage</div>
          <q-input v-model="form.image_url" label="URL image" outlined dense bottom-slots />
          <div class="row items-center" style="gap: 16px">
            <q-toggle v-model="form.is_featured" label="Produit en vedette" />
            <q-input
              v-if="form.is_featured"
              v-model.number="form.featured_position"
              label="Position vedette"
              type="number"
              outlined
              dense
              style="max-width: 160px"
            />
          </div>

          <div class="row justify-end q-mt-md" style="gap: 8px">
            <q-btn flat label="Annuler" :disable="saving" @click="emit('update:modelValue', false)" />
            <q-btn
              type="submit"
              color="primary"
              :label="isEdit ? 'Enregistrer' : 'Créer'"
              :loading="saving"
            />
          </div>
        </q-form>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import { listCategories, type Category } from 'src/api/categories';
import { listTaxRates, type TaxRate } from 'src/api/taxRates';
import { listPlaces, type Place } from 'src/api/logistics';
import { useProductsStore, type ProductPublic } from 'src/stores/products';

const props = defineProps<{ modelValue: boolean; product: ProductPublic | null }>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [];
}>();

const store = useProductsStore();

interface FormState {
  name: string;
  description: string;
  long_description: string;
  cost_amount: string;
  cost_currency: string;
  customs_rate_pct: string;
  base_price: string;
  category_id: string | null;
  tax_rate_id: string | null;
  supplier_place_id: string | null;
  weight: number | null;
  dimensions_length: number | null;
  dimensions_width: number | null;
  dimensions_height: number | null;
  image_url: string;
  is_featured: boolean;
  featured_position: number | null;
}

/** Fields sent as decimal strings — never null (backend columns are non-nullable). */
const MONEY_FIELDS = ['cost_amount', 'customs_rate_pct', 'base_price'] as const;

function emptyForm(): FormState {
  return {
    name: '',
    description: '',
    long_description: '',
    cost_amount: '0.00',
    cost_currency: 'XPF',
    customs_rate_pct: '0.00',
    base_price: '0.00',
    category_id: null,
    tax_rate_id: null,
    supplier_place_id: null,
    weight: null,
    dimensions_length: null,
    dimensions_width: null,
    dimensions_height: null,
    image_url: '',
    is_featured: false,
    featured_position: null,
  };
}

const form = reactive<FormState>(emptyForm());
let original: FormState = emptyForm();

const saving = ref(false);
const error = ref<string | null>(null);
const req = [(v: string) => (!!v && v.trim().length > 0) || 'Requis'];

const currencyOptions = [
  { label: 'XPF', value: 'XPF' },
  { label: 'USD', value: 'USD' },
  { label: 'EUR', value: 'EUR' },
];
const categories = ref<Category[]>([]);
const taxRates = ref<TaxRate[]>([]);
const places = ref<Place[]>([]);
const categoryOptions = ref<{ label: string; value: string }[]>([]);
const taxRateOptions = ref<{ label: string; value: string }[]>([]);
const placeOptions = ref<{ label: string; value: string }[]>([]);

const isEdit = ref(false);

function str(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return '';
}
function num(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function loadFromProduct(p: ProductPublic | null) {
  const base = emptyForm();
  if (p) {
    const rec = p as unknown as Record<string, unknown>;
    base.name = str(rec.name);
    base.description = str(rec.description);
    base.long_description = str(rec.long_description);
    base.cost_amount = str(rec.cost_amount) || '0.00';
    base.cost_currency = str(rec.cost_currency) || 'XPF';
    base.customs_rate_pct = str(rec.customs_rate_pct) || '0.00';
    base.base_price = str(rec.base_price) || '0.00';
    base.category_id = (rec.category_id as string | null) ?? null;
    base.tax_rate_id = (rec.tax_rate_id as string | null) ?? null;
    base.supplier_place_id = (rec.supplier_place_id as string | null) ?? null;
    base.weight = num(rec.weight);
    base.dimensions_length = num(rec.dimensions_length);
    base.dimensions_width = num(rec.dimensions_width);
    base.dimensions_height = num(rec.dimensions_height);
    base.image_url = str(rec.image_url);
    base.is_featured = Boolean(rec.is_featured);
    base.featured_position = num(rec.featured_position);
  }
  Object.assign(form, base);
  original = { ...base };
}

/** Build the payload: full for create, only changed fields for edit. */
function buildPayload(): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const keys = Object.keys(form) as (keyof FormState)[];
  for (const key of keys) {
    const value = form[key];
    if (isEdit.value && value === original[key]) continue;
    if (MONEY_FIELDS.includes(key as (typeof MONEY_FIELDS)[number])) {
      out[key] = str(value).trim() || '0.00';
    } else if (typeof value === 'string') {
      out[key] = value.trim() === '' ? null : value.trim();
    } else {
      out[key] = value;
    }
  }
  // `name` is required — never send it as null even if blanked.
  if (out.name == null && !isEdit.value) out.name = form.name.trim();
  return out;
}

async function onSubmit() {
  saving.value = true;
  error.value = null;
  try {
    const payload = buildPayload();
    if (isEdit.value && props.product) {
      await store.updateProduct(props.product.id, payload);
    } else {
      await store.createProduct(payload);
    }
    emit('saved');
    emit('update:modelValue', false);
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function loadLookups() {
  try {
    [categories.value, taxRates.value, places.value] = await Promise.all([
      listCategories(),
      listTaxRates({ valid: true }),
      listPlaces(),
    ]);
    categoryOptions.value = categories.value.map((c) => ({ label: c.name, value: c.id }));
    taxRateOptions.value = taxRates.value.map((t) => ({
      label: `${t.label} (${t.rate_pct}%)`,
      value: t.id,
    }));
    placeOptions.value = places.value.map((p) => ({
      label: p.code ? `${p.name} (${p.code})` : p.name,
      value: p.id,
    }));
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Chargement des listes impossible.';
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      isEdit.value = !!props.product;
      error.value = null;
      loadFromProduct(props.product);
    }
  },
);

onMounted(() => {
  void loadLookups();
});
</script>
