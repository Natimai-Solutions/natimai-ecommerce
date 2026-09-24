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
          <strong>verrouillés</strong> : ni la synchronisation ni l'enrichissement Icecat ne les
          réécriront.
        </q-banner>

        <div v-if="isEdit && lockedFields.length" class="q-mb-md">
          <div class="text-caption text-grey-7 q-mb-xs">
            Champs verrouillés — cliquez pour libérer (la valeur fournisseur reviendra à la
            prochaine synchronisation ou au prochain enrichissement) :
          </div>
          <q-chip
            v-for="field in lockedFields"
            :key="field"
            dense
            removable
            icon="lock"
            color="orange-2"
            text-color="orange-10"
            :label="fieldLabel(field)"
            :disable="releasing === field"
            @remove="onRelease(field)"
          />
        </div>

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

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Approvisionnement</div>
          <div class="row" style="gap: 8px">
            <q-select
              v-model="form.supplier_name"
              :options="supplierOptions"
              label="Fournisseur"
              hint="Vide = article de votre entrepôt, sans fournisseur"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              clearable
              class="col"
              :disable="isEdit && !!product?.is_supplier_managed"
              @update:model-value="onSupplierChange"
            />
            <q-input
              v-model="form.supplier_sku"
              label="Référence chez le fournisseur"
              outlined
              dense
              bottom-slots
              class="col"
            />
          </div>
          <q-input
            v-if="form.supplier_name && !product?.is_supplier_managed"
            v-model="form.supplier_quantity"
            label="Stock disponible chez le fournisseur"
            hint="Tenu à jour à la main (ou par import fichier) — 0 = indisponible"
            type="number"
            step="1"
            min="0"
            outlined
            dense
            bottom-slots
          />

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Disponibilité</div>
          <q-option-group
            v-model="form.availability_mode"
            :options="availabilityModeOptions"
            inline
            dense
          />
          <div class="text-caption text-grey-7 q-mb-sm">{{ availabilityModeHint }}</div>

          <div class="text-subtitle2 q-mt-sm q-mb-xs">Prix &amp; taxes</div>
          <q-option-group
            v-model="form.pricing_mode"
            :options="pricingModeOptions"
            inline
            dense
          />
          <div class="text-caption text-grey-7 q-mb-sm">{{ pricingModeHint }}</div>

          <template v-if="form.pricing_mode === 'fixed'">
            <q-input
              v-model="form.base_price"
              label="Prix de vente TTC *"
              hint="Prix affiché tel quel, taxes comprises"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
              bottom-slots
            />
          </template>
          <template v-else>
            <div class="row" style="gap: 8px">
              <q-input
                v-model="form.cost_amount"
                label="Coût d'achat"
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
                v-if="form.pricing_mode === 'import'"
                v-model="form.customs_rate_pct"
                label="Douane (%)"
                hint="Vide = taux par défaut de la catégorie"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-input
                v-model="form.margin_rate_pct"
                label="Marge (%)"
                hint="Vide = marge de la catégorie, sinon du groupe tarifaire"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
            </div>
          </template>
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
            <q-btn
              flat
              label="Annuler"
              :disable="saving"
              @click="emit('update:modelValue', false)"
            />
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
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { categoryLabel, listCategories, type Category } from 'src/api/categories';
import { listTaxRates, type TaxRate } from 'src/api/taxRates';
import { listPlaces, type Place } from 'src/api/logistics';
import { listSuppliers, type Supplier } from 'src/api/suppliers';
import { useProductsStore, type ProductPublic } from 'src/stores/products';

const props = defineProps<{ modelValue: boolean; product: ProductPublic | null }>();
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [];
}>();

const store = useProductsStore();

type PricingMode = 'import' | 'domestic' | 'fixed';
type AvailabilityMode = 'stock' | 'on_demand' | 'continuous';

interface FormState {
  name: string;
  description: string;
  long_description: string;
  supplier_name: string | null;
  supplier_sku: string;
  supplier_quantity: string;
  pricing_mode: PricingMode;
  availability_mode: AvailabilityMode;
  margin_rate_pct: string;
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
const MONEY_FIELDS = ['cost_amount', 'base_price'] as const;

/**
 * Sent as a decimal string too, but blank means null: the product then inherits
 * its category's default customs rate. Defaulting it to '0.00' like the other
 * money fields would freeze a duty-free price on every product the admin ever
 * opens — the very bug the category default was introduced to fix.
 */
const NULLABLE_RATE_FIELDS = ['customs_rate_pct', 'margin_rate_pct'] as const;
/** Decimal string, blank → '0.00' (the column is non-nullable). */
const QUANTITY_FIELDS = ['supplier_quantity'] as const;

function emptyForm(): FormState {
  return {
    name: '',
    description: '',
    long_description: '',
    supplier_name: null,
    supplier_sku: '',
    supplier_quantity: '0',
    pricing_mode: 'import',
    availability_mode: 'stock',
    margin_rate_pct: '',
    cost_amount: '0.00',
    cost_currency: 'XPF',
    customs_rate_pct: '',
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
const suppliers = ref<Supplier[]>([]);
const supplierOptions = ref<{ label: string; value: string }[]>([]);

const pricingModeOptions: { label: string; value: PricingMode }[] = [
  { label: 'Import (CAF + douane)', value: 'import' },
  { label: 'Local (coût + marge)', value: 'domestic' },
  { label: 'Prix TTC fixé', value: 'fixed' },
];
const PRICING_MODE_HINTS: Record<PricingMode, string> = {
  import:
    'Coût + fret import + assurance, puis douane, marge et taxe. Douane et poids obligatoires pour la publication.',
  domestic:
    'Article de votre entrepôt ou d’un fournisseur du même territoire douanier : coût, marge, taxe — ni douane ni fret import.',
  fixed: 'Vous saisissez le prix de vente TTC ; rien n’est recalculé.',
};
const pricingModeHint = computed(() => PRICING_MODE_HINTS[form.pricing_mode]);

const availabilityModeOptions: { label: string; value: AvailabilityMode }[] = [
  { label: 'Selon le stock', value: 'stock' },
  { label: 'Sur commande', value: 'on_demand' },
  { label: 'Toujours commandable', value: 'continuous' },
];
const AVAILABILITY_MODE_HINTS: Record<AvailabilityMode, string> = {
  stock: 'Commandable seulement si le stock (local + fournisseur) couvre la quantité ; réservé au checkout.',
  on_demand:
    'Précommande : commandable tant que le fournisseur affiche du stock, sans réservation — acheté à la clôture du départ groupé.',
  continuous: 'Toujours commandable, même sans stock connu ; expédié avec le prochain départ groupé.',
};
const availabilityModeHint = computed(() => AVAILABILITY_MODE_HINTS[form.availability_mode]);

/**
 * Choosing a supplier pre-fills what the supplier decides: its origin
 * warehouse (first logistics leg) and its customs regime (pricing mode).
 * Both stay editable — the admin has the last word.
 */
function onSupplierChange(code: string | null) {
  const supplier = suppliers.value.find((s) => s.code === code);
  if (!supplier) return;
  if (supplier.origin_place_id) form.supplier_place_id = supplier.origin_place_id;
  if (form.pricing_mode !== 'fixed') {
    form.pricing_mode = supplier.is_domestic ? 'domestic' : 'import';
  }
  if (supplier.price_currency) form.cost_currency = supplier.price_currency;
}
const categoryOptions = ref<{ label: string; value: string }[]>([]);
const taxRateOptions = ref<{ label: string; value: string }[]>([]);
const placeOptions = ref<{ label: string; value: string }[]>([]);

const isEdit = ref(false);

/** Libellés des champs verrouillables, pour les puces de verrous. */
const FIELD_LABELS: Record<string, string> = {
  name: 'Nom',
  description: 'Description courte',
  long_description: 'Description longue',
  supplier_name: 'Fournisseur',
  supplier_sku: 'Référence fournisseur',
  supplier_quantity: 'Stock fournisseur',
  pricing_mode: 'Mode de prix',
  availability_mode: 'Disponibilité',
  margin_rate_pct: 'Marge',
  cost_amount: 'Coût',
  cost_currency: 'Devise du coût',
  customs_rate_pct: 'Douane',
  base_price: 'Prix de vente',
  category_id: 'Catégorie',
  tax_rate_id: 'Taux de TVA',
  supplier_place_id: 'Origine',
  weight: 'Poids',
  dimensions_length: 'Longueur',
  dimensions_width: 'Largeur',
  dimensions_height: 'Hauteur',
  image_url: 'Image',
  is_featured: 'Vedette',
  featured_position: 'Position vedette',
};
function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

const lockedFields = ref<string[]>([]);
const releasing = ref<string | null>(null);

async function onRelease(field: string) {
  if (!props.product) return;
  releasing.value = field;
  error.value = null;
  try {
    const refreshed = await store.releaseOverride(props.product.id, field);
    lockedFields.value = [...(refreshed.overridden_fields ?? [])];
    emit('saved');
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Libération impossible.';
  } finally {
    releasing.value = null;
  }
}

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
    base.supplier_name = (rec.supplier_name as string | null) ?? null;
    base.supplier_sku = str(rec.supplier_sku);
    base.supplier_quantity = str(rec.supplier_quantity) || '0';
    const mode = str(rec.pricing_mode);
    base.pricing_mode = mode === 'domestic' || mode === 'fixed' ? mode : 'import';
    const availability = str(rec.availability_mode);
    base.availability_mode =
      availability === 'on_demand' || availability === 'continuous' ? availability : 'stock';
    base.margin_rate_pct = str(rec.margin_rate_pct);
    base.cost_amount = str(rec.cost_amount) || '0.00';
    base.cost_currency = str(rec.cost_currency) || 'XPF';
    base.customs_rate_pct = str(rec.customs_rate_pct);
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
    } else if (QUANTITY_FIELDS.includes(key as (typeof QUANTITY_FIELDS)[number])) {
      out[key] = str(value).trim() || '0';
    } else if (NULLABLE_RATE_FIELDS.includes(key as (typeof NULLABLE_RATE_FIELDS)[number])) {
      out[key] = str(value).trim() || null;
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
    [categories.value, taxRates.value, places.value, suppliers.value] = await Promise.all([
      listCategories(),
      listTaxRates({ valid: true }),
      listPlaces(),
      listSuppliers(),
    ]);
    supplierOptions.value = suppliers.value
      .filter((s) => s.is_active)
      .map((s) => ({
        label: `${s.name}${s.is_domestic ? ' (local)' : ''} — ${s.code}`,
        value: s.code,
      }));
    categoryOptions.value = categories.value.map((c) => ({ label: categoryLabel(c), value: c.id }));
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
      lockedFields.value = [...(props.product?.overridden_fields ?? [])];
      loadFromProduct(props.product);
    }
  },
);

onMounted(() => {
  void loadLookups();
});
</script>
