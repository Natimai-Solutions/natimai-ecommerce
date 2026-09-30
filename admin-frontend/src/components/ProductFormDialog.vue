<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog app-dialog--xl">
      <q-form @submit="onSubmit">
        <q-card-section class="app-dialog__head">
          <div class="product-form__head">
            <h2 class="app-dialog__title">
              {{ isEdit ? 'Modifier le produit' : 'Nouveau produit' }}
            </h2>
            <StatusTag
              v-if="isEdit && product?.is_supplier_managed"
              label="Fournisseur"
              icon="ph:truck"
            />
            <StatusTag v-else-if="isEdit" label="Manuel" icon="ph:hand" />
          </div>
        </q-card-section>

        <q-card-section>
          <div v-if="error || (isEdit && product?.is_supplier_managed)" class="admin-notices">
            <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
            <AppNotice v-if="isEdit && product?.is_supplier_managed" tone="info" dense>
              Produit synchronisé depuis un fournisseur. Les champs que vous modifiez ici seront
              <strong>verrouillés</strong> : ni la synchronisation ni l'enrichissement Icecat ne les
              réécriront.
            </AppNotice>
          </div>

          <div v-if="isEdit && lockedFields.length" class="q-mb-md">
            <p class="admin-hint q-mb-xs">
              Champs verrouillés — cliquez pour libérer (la valeur fournisseur reviendra à la
              prochaine synchronisation ou au prochain enrichissement) :
            </p>
            <q-chip
              v-for="field in lockedFields"
              :key="field"
              dense
              removable
              icon="ph:lock"
              :label="fieldLabel(field)"
              :disable="releasing === field"
              @remove="onRelease(field)"
            />
          </div>

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

          <div class="product-form__grid">
            <div>
              <h3 v-if="suppliersOn" class="admin-subtitle">Approvisionnement</h3>
              <div v-if="suppliersOn" class="row" style="gap: 8px">
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
                  :disable="isEdit && linkedManaged"
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
              <div
                v-if="suppliersOn && isEdit && product && !product.has_variants"
                class="row items-center q-mb-sm"
                style="gap: 8px"
              >
                <q-btn
                  v-if="!linkedManaged"
                  outline
                  dense
                  no-caps
                  icon="ph:link"
                  label="Rattacher maintenant"
                  :disable="!form.supplier_name || !form.supplier_sku.trim()"
                  :loading="linking === 'attach'"
                  data-testid="product-attach-supplier"
                  @click="onAttach"
                >
                  <q-tooltip>
                    Interroge le fournisseur sur cette référence et reprend coût et stock tout de
                    suite ; vos textes restent verrouillés
                  </q-tooltip>
                </q-btn>
                <q-btn
                  v-if="linkedManaged || (managedAfterLink === null && product.supplier_name)"
                  flat
                  dense
                  no-caps
                  icon="ph:link-break"
                  label="Détacher"
                  :loading="linking === 'detach'"
                  data-testid="product-detach-supplier"
                  @click="onDetach"
                >
                  <q-tooltip>
                    L'article redevient manuel : plus de synchronisation, stock fournisseur à zéro
                  </q-tooltip>
                </q-btn>
              </div>
              <AppNotice v-if="linkNotice" tone="success" dense class="q-mb-sm">
                {{ linkNotice }}
              </AppNotice>
              <q-input
                v-if="suppliersOn && form.supplier_name && !product?.is_supplier_managed"
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
              <q-input
                v-model="form.local_quantity"
                label="Stock entrepôt (unités physiquement chez vous)"
                :hint="localStockHint"
                type="number"
                step="1"
                min="0"
                outlined
                dense
                bottom-slots
              />
            </div>

            <div>
              <h3 class="admin-subtitle">État</h3>
              <q-option-group v-model="form.condition" :options="conditionOptions" inline dense />
              <div v-if="form.condition === 'refurbished'" class="row q-col-gutter-sm q-mb-sm">
                <q-input
                  v-model="form.condition_grade"
                  class="col-6"
                  label="Grade"
                  hint="A, B, C…"
                  outlined
                  dense
                  maxlength="5"
                />
                <q-input
                  v-model="form.battery_health_pct"
                  class="col-6"
                  type="number"
                  min="0"
                  max="100"
                  label="Batterie (%)"
                  outlined
                  dense
                />
                <q-input
                  v-model="form.os_licence"
                  class="col-6"
                  label="Licence OS"
                  outlined
                  dense
                />
                <q-input
                  v-model="form.warranty_months"
                  class="col-6"
                  type="number"
                  min="0"
                  label="Garantie (mois)"
                  outlined
                  dense
                />
              </div>

              <h3 class="admin-subtitle q-mt-md">Disponibilité</h3>
              <q-option-group
                v-model="form.availability_mode"
                :options="availabilityModeOptions"
                inline
                dense
              />
              <p class="product-form__help">{{ availabilityModeHint }}</p>
            </div>

            <div>
              <h3 class="admin-subtitle">Prix &amp; taxes</h3>
              <q-option-group
                v-model="form.pricing_mode"
                :options="pricingModeOptions"
                inline
                dense
              />
              <p class="product-form__help">{{ pricingModeHint }}</p>

              <q-input
                v-if="form.pricing_mode === 'fixed'"
                v-model="form.base_price"
                label="Prix de vente TTC *"
                hint="Prix affiché tel quel, taxes comprises"
                type="number"
                step="0.01"
                min="0"
                outlined
                dense
                bottom-slots
                data-testid="product-base-price"
              />
              <div class="row" style="gap: 8px">
                <q-input
                  v-model="form.cost_amount"
                  :label="form.pricing_mode === 'fixed' ? 'Coût d\'achat HT' : 'Coût d\'achat'"
                  :hint="
                    form.pricing_mode === 'fixed' ? 'Sert au calcul de la marge (0 = inconnu)' : ''
                  "
                  type="number"
                  step="0.01"
                  min="0"
                  outlined
                  dense
                  bottom-slots
                  class="col"
                  data-testid="product-cost"
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
              <div v-if="form.pricing_mode !== 'fixed'" class="row" style="gap: 8px">
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
                  label="Taux de TVA"
                  hint="Vide = taux de la catégorie, sinon taux par défaut"
                  outlined
                  dense
                  bottom-slots
                  emit-value
                  map-options
                  clearable
                  class="col"
                />
              </div>
              <MarginPreviewPanel
                v-if="modelValue"
                v-model:group-prices="groupPrices"
                :input="marginInput"
              />
            </div>

            <div>
              <h3 class="admin-subtitle">Logistique</h3>
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
            </div>

            <div>
              <h3 class="admin-subtitle">Affichage</h3>
              <q-input
                v-model="form.image_url"
                label="Image"
                hint="Choisissez une image de la médiathèque ou collez une URL"
                outlined
                dense
                bottom-slots
              >
                <template v-if="form.image_url" #prepend>
                  <img :src="form.image_url" alt="" class="image-field__thumb" />
                </template>
                <template #append>
                  <q-btn
                    flat
                    dense
                    no-caps
                    icon="ph:images"
                    label="Médiathèque"
                    @click="mediaPickerOpen = true"
                  />
                </template>
              </q-input>
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
            </div>
          </div>

          <template v-if="isEdit && product && !product.parent_product_id">
            <q-separator class="q-my-lg" />
            <ProductVariantsPanel :product-id="product.id" @changed="emit('saved')" />
          </template>
          <p v-else-if="isEdit && product?.parent_product_id" class="admin-hint q-mt-md q-mb-none">
            Variante d'un autre article
            <span v-if="product.variant_options">
              ({{
                Object.entries(product.variant_options)
                  .map(([k, v]) => `${k} : ${v}`)
                  .join(', ')
              }})
            </span>
            — les options se modifient depuis la fiche parente.
          </p>
        </q-card-section>

        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn
            flat
            no-caps
            label="Annuler"
            :disable="saving"
            @click="emit('update:modelValue', false)"
          />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="isEdit ? 'Enregistrer' : 'Créer'"
            :loading="saving"
          />
        </q-card-actions>
      </q-form>
    </q-card>
    <MediaPicker
      v-model="mediaPickerOpen"
      kind="product"
      @select="(asset) => (form.image_url = asset.url)"
    />
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useQuasar } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { categoryLabel, listCategories, type Category } from '@/api/categories';
import { listTaxRates, type TaxRate } from '@/api/taxRates';
import { listPlaces, type Place } from '@/api/logistics';
import {
  attachProductToSupplier,
  detachProductFromSupplier,
  listSuppliers,
  type Supplier,
} from '@/api/suppliers';
import { extractApiError } from '@/api/errors';
import { adjustInventory } from '@/api/inventory';
import MarginPreviewPanel from '@/components/MarginPreviewPanel.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import { getGroupPrices, setGroupPrices, type MarginPreviewRequest } from '@/api/margin';
import ProductVariantsPanel from '@/components/ProductVariantsPanel.vue';
import { useProductsStore, type ProductPublic } from '@/stores/products';
import { useShopConfigStore } from '@/stores/shopConfig';

const props = defineProps<{ modelValue: boolean; product: ProductPublic | null }>();
const mediaPickerOpen = ref(false);
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [];
}>();

const store = useProductsStore();
const shopConfig = useShopConfigStore();
/** SHOP_MODE=simple: own stock sold at a fixed price, no supplier, no customs. */
const isSimpleShop = computed(() => shopConfig.isSimple);
/** Supply block (supplier, reference, attach): the suppliers module. */
const suppliersOn = computed(() => shopConfig.moduleOn('suppliers'));

type PricingMode = 'import' | 'domestic' | 'fixed';
type AvailabilityMode = 'stock' | 'on_demand' | 'continuous' | 'lot';
type ProductCondition = 'new' | 'refurbished';

interface FormState {
  name: string;
  description: string;
  long_description: string;
  supplier_name: string | null;
  supplier_sku: string;
  supplier_quantity: string;
  /** Stock entrepôt — pas un champ produit : enregistré par un ajustement d'inventaire. */
  local_quantity: string;
  pricing_mode: PricingMode;
  availability_mode: AvailabilityMode;
  condition: ProductCondition;
  condition_grade: string;
  battery_health_pct: string;
  os_licence: string;
  warranty_months: string;
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
    local_quantity: '0',
    pricing_mode: isSimpleShop.value ? 'fixed' : 'import',
    availability_mode: 'stock',
    condition: 'new',
    condition_grade: '',
    battery_health_pct: '',
    os_licence: '',
    warranty_months: '',
    margin_rate_pct: '',
    cost_amount: '0.00',
    cost_currency: shopConfig.currency,
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

const currencyOptions = computed(() => {
  const codes = Array.from(new Set([shopConfig.currency, 'XPF', 'USD', 'EUR']));
  return codes.map((code) => ({ label: code, value: code }));
});
const categories = ref<Category[]>([]);
const taxRates = ref<TaxRate[]>([]);
const places = ref<Place[]>([]);
const suppliers = ref<Supplier[]>([]);
const supplierOptions = ref<{ label: string; value: string }[]>([]);

const allPricingModeOptions: { label: string; value: PricingMode }[] = [
  { label: 'Import (CAF + douane)', value: 'import' },
  { label: 'Local (coût + marge)', value: 'domestic' },
  { label: 'Prix TTC fixé', value: 'fixed' },
];
const pricingModeOptions = computed(() =>
  isSimpleShop.value
    ? allPricingModeOptions.filter((o) => o.value !== 'import')
    : allPricingModeOptions,
);
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
  { label: 'Lot (quantité fixe)', value: 'lot' },
];
const conditionOptions: { label: string; value: ProductCondition }[] = [
  { label: 'Neuf', value: 'new' },
  { label: 'Reconditionné', value: 'refurbished' },
];
const AVAILABILITY_MODE_HINTS: Record<AvailabilityMode, string> = {
  stock:
    'Commandable seulement si le stock (local + fournisseur) couvre la quantité ; réservé au checkout.',
  on_demand:
    'Précommande : commandable tant que le fournisseur affiche du stock, sans réservation — acheté à la clôture du départ groupé.',
  continuous:
    'Toujours commandable, même sans stock connu ; expédié avec le prochain départ groupé.',
  lot: 'Lot reconditionné : le « stock fournisseur » est la taille du lot, décrémentée à chaque commande ; à zéro le lot est épuisé. Saisi ici, il n’est pas écrasé par la synchronisation.',
};
const availabilityModeHint = computed(() => AVAILABILITY_MODE_HINTS[form.availability_mode]);

/**
 * The warehouse stock is what the checkout serves first; for a product with
 * no supplier it is the only sellable stock. Saved through the audited
 * inventory adjustment (a stock movement is written), not as a product field.
 */
const localStockHint = computed(() =>
  form.supplier_name || props.product?.is_supplier_managed
    ? 'Servi en premier au checkout, avant la dispo fournisseur. Un mouvement de stock est tracé.'
    : 'Sans fournisseur, c’est le seul stock vendable en boutique. Un mouvement de stock est tracé.',
);

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

// Prix saisis par groupe de clients (group id → prix TTC) ; null tant que ceux
// de l'article ne sont pas chargés (l'aperçu prend alors ceux enregistrés).
const groupPrices = ref<Record<string, string> | null>(null);
let storedGroupPrices: Record<string, string> = {};

async function loadGroupPrices(product: ProductPublic | null) {
  groupPrices.value = null;
  storedGroupPrices = {};
  if (!product) {
    groupPrices.value = {};
    return;
  }
  try {
    storedGroupPrices = await getGroupPrices(product.id);
  } catch {
    storedGroupPrices = {};
  }
  groupPrices.value = { ...storedGroupPrices };
}

/** Enregistre les prix par groupe modifiés (après l'article lui-même). */
async function saveGroupPrices(productId: string) {
  if (groupPrices.value === null) return;
  const current = groupPrices.value;
  const ids = new Set([...Object.keys(storedGroupPrices), ...Object.keys(current)]);
  const changes = [...ids]
    .filter((id) => (current[id] ?? '') !== (storedGroupPrices[id] ?? ''))
    .map((id) => ({
      price_group_id: id,
      price: current[id] ? String(Number(current[id])) : null,
    }));
  if (changes.length) await setGroupPrices(productId, changes);
}

/** Valeurs de prix du formulaire, envoyées à l'aperçu de marge. */
const marginInput = computed<MarginPreviewRequest>(() => ({
  group_prices: groupPrices.value,
  product_id: isEdit.value ? (props.product?.id ?? null) : null,
  pricing_mode: form.pricing_mode,
  base_price: decimalOrNull(form.base_price),
  cost_amount: decimalOrNull(form.cost_amount),
  cost_currency: form.cost_currency || null,
  margin_rate_pct: decimalOrNull(form.margin_rate_pct),
  customs_rate_pct: decimalOrNull(form.customs_rate_pct),
  tax_rate_id: form.tax_rate_id,
  category_id: form.category_id,
}));

function decimalOrNull(value: string | number | null): string | null {
  const text = String(value ?? '').trim();
  return text === '' || Number.isNaN(Number(text)) ? null : String(Number(text));
}
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
  condition: 'État',
  condition_grade: 'Grade',
  battery_health_pct: 'Batterie (%)',
  os_licence: 'Licence OS',
  warranty_months: 'Garantie (mois)',
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

const $q = useQuasar();
const linking = ref<'attach' | 'detach' | null>(null);
const linkNotice = ref<string | null>(null);
/** Supplier state after an attach / detach in this dialog (the prop is stale). */
const managedAfterLink = ref<boolean | null>(null);
const linkedManaged = computed<boolean>(() =>
  managedAfterLink.value !== null ? managedAfterLink.value : !!props.product?.is_supplier_managed,
);

async function onAttach() {
  if (!props.product) return;
  linking.value = 'attach';
  error.value = null;
  linkNotice.value = null;
  try {
    const res = await attachProductToSupplier(props.product.id, {
      supplier_name: form.supplier_name,
      supplier_sku: form.supplier_sku.trim(),
    });
    linkNotice.value = res.message;
    managedAfterLink.value = !!res.product.is_supplier_managed;
    lockedFields.value = [...(res.product.overridden_fields ?? [])];
    emit('saved');
  } catch (err: unknown) {
    error.value = extractApiError(err) ?? 'Rattachement impossible.';
  } finally {
    linking.value = null;
  }
}

function onDetach() {
  const product = props.product;
  if (!product) return;
  $q.dialog({
    title: 'Détacher du fournisseur ?',
    message:
      "L'article redevient manuel : plus aucune synchronisation, son stock fournisseur passe à " +
      'zéro. Vos champs verrouillés restent tels quels. Un prochain import contenant la même ' +
      'référence créera un nouvel article.',
    cancel: { flat: true, noCaps: true, label: 'Annuler' },
    ok: { color: 'negative', unelevated: true, noCaps: true, label: 'Détacher' },
  }).onOk(() => {
    void (async () => {
      linking.value = 'detach';
      error.value = null;
      linkNotice.value = null;
      try {
        await detachProductFromSupplier(product.id);
        form.supplier_name = null;
        managedAfterLink.value = false;
        linkNotice.value = 'Article détaché : il est désormais géré à la main.';
        emit('saved');
      } catch (err: unknown) {
        error.value = extractApiError(err) ?? 'Détachement impossible.';
      } finally {
        linking.value = null;
      }
    })();
  });
}

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
/** Decimal string from the API ("12.00") → integer text for the field ("12"). */
function formatQty(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.max(0, Math.round(n))) : '0';
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
    base.local_quantity = formatQty(rec.local_quantity);
    const mode = str(rec.pricing_mode);
    base.pricing_mode = mode === 'domestic' || mode === 'fixed' ? mode : 'import';
    const availability = str(rec.availability_mode);
    base.availability_mode =
      availability === 'on_demand' || availability === 'continuous' || availability === 'lot'
        ? availability
        : 'stock';
    base.condition = str(rec.condition) === 'refurbished' ? 'refurbished' : 'new';
    base.condition_grade = str(rec.condition_grade);
    base.battery_health_pct = str(rec.battery_health_pct);
    base.os_licence = str(rec.os_licence);
    base.warranty_months = str(rec.warranty_months);
    base.margin_rate_pct = str(rec.margin_rate_pct);
    base.cost_amount = str(rec.cost_amount) || '0.00';
    base.cost_currency = str(rec.cost_currency) || shopConfig.currency;
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
    if (key === 'local_quantity') continue; // inventory adjustment, not a product field
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
    let productId: string;
    if (isEdit.value && props.product) {
      await store.updateProduct(props.product.id, payload);
      productId = props.product.id;
    } else {
      productId = (await store.createProduct(payload)).id;
    }
    await saveLocalStock(productId);
    await saveGroupPrices(productId);
    emit('saved');
    emit('update:modelValue', false);
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

/**
 * Warehouse stock goes through the audited inventory adjustment (the same
 * one as the « Inventaire » page): the quantity becomes the new absolute
 * local stock and a movement records the delta. Nothing is sent when it did
 * not change, so an edit never rewrites the stock silently.
 */
async function saveLocalStock(productId: string) {
  const next = formatQty(form.local_quantity);
  const previous = formatQty(original.local_quantity);
  if (next === previous) return;
  await adjustInventory({
    product_id: productId,
    place_id: null,
    quantity: next,
    reason: isEdit.value
      ? 'Modification depuis la fiche produit'
      : 'Stock initial saisi à la création',
  });
}

async function loadLookups() {
  void shopConfig.load();
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
      linkNotice.value = null;
      managedAfterLink.value = null;
      lockedFields.value = [...(props.product?.overridden_fields ?? [])];
      loadFromProduct(props.product);
      void loadGroupPrices(props.product);
    }
  },
);

onMounted(() => {
  void loadLookups();
});
</script>

<style scoped lang="scss">
.product-form__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.product-form__grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 32px;

  @media (max-width: 899px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.product-form__help {
  margin: 4px 0 12px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

.image-field__thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
</style>
