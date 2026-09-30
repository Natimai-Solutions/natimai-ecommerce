<template>
  <div>
    <div class="row items-center q-mb-xs">
      <h3 class="admin-subtitle col q-mb-none">Variantes</h3>
      <q-btn flat dense no-caps icon="ph:plus" label="Ajouter une variante" @click="openCreate" />
    </div>
    <p class="admin-hint q-mb-sm">
      Chaque variante (taille, couleur…) est un article à part entière : référence, prix, coût,
      stock, image. La fiche parente est l'entrée boutique et affiche le prix le plus bas ; elle
      n'est jamais vendue telle quelle.
    </p>

    <AppNotice v-if="error" tone="error" dense class="q-mb-sm">{{ error }}</AppNotice>

    <q-markup-table v-if="variants.length" dense flat bordered class="q-mb-sm">
      <thead>
        <tr>
          <th v-for="axis in axes" :key="axis" class="text-left">{{ axis }}</th>
          <th class="text-left">Référence</th>
          <th class="text-right">Prix</th>
          <th class="text-right">Stock</th>
          <th class="text-center">Actif</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="v in variants" :key="v.id" :class="{ 'text-subtle': !v.is_active }">
          <td v-for="axis in axes" :key="axis">{{ v.variant_options?.[axis] ?? '—' }}</td>
          <td class="font-mono">{{ v.supplier_sku || v.vendor_part_number || '—' }}</td>
          <td class="text-right font-mono">{{ money(v.sale_price_cached ?? v.base_price) }}</td>
          <td class="text-right">
            <span class="font-mono">{{ qty(v.available_quantity) }}</span>
            <span class="text-caption text-muted">
              (entrepôt {{ qty(v.local_quantity) }} · fourn. {{ qty(v.supplier_quantity) }})
            </span>
          </td>
          <td class="text-center">
            <StatusTag v-if="v.is_active" label="Active" tone="ok" icon="ph:check-circle" />
            <StatusTag v-else label="Inactive" tone="neutral" icon="ph:minus-circle" />
          </td>
          <td class="text-right no-wrap">
            <q-btn flat dense round icon="ph:pencil-simple" size="sm" @click="openEdit(v)">
              <q-tooltip>Modifier</q-tooltip>
            </q-btn>
            <q-btn
              v-if="v.is_active"
              flat
              dense
              round
              icon="ph:trash"
              size="sm"
              color="negative"
              :loading="busyId === v.id"
              @click="onDeactivate(v)"
            >
              <q-tooltip>Retirer (les commandes passées gardent la référence)</q-tooltip>
            </q-btn>
          </td>
        </tr>
      </tbody>
    </q-markup-table>
    <div v-else-if="!loading" class="text-caption text-subtle q-mb-sm">
      Aucune variante : l'article se vend tel quel.
    </div>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editing ? 'Modifier la variante' : 'Nouvelle variante' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>

            <div class="text-caption text-muted">Options (ex. Taille = M, Couleur = Noir)</div>
            <div v-for="(row, i) in optionRows" :key="i" class="row q-col-gutter-xs items-center">
              <q-input v-model="row.name" label="Option" outlined dense class="col-5" />
              <q-input v-model="row.value" label="Valeur" outlined dense class="col-5" />
              <q-btn flat dense round icon="ph:x" class="col-1" @click="optionRows.splice(i, 1)">
                <q-tooltip>Retirer l'option</q-tooltip>
              </q-btn>
            </div>
            <q-btn
              flat
              dense
              no-caps
              icon="ph:plus"
              label="Ajouter une option"
              @click="optionRows.push({ name: '', value: '' })"
            />

            <q-input
              v-model="form.name"
              label="Nom affiché (vide = parent + options)"
              outlined
              dense
            />
            <div class="row q-col-gutter-sm">
              <q-input v-model="form.supplier_sku" label="Référence" outlined dense class="col-6" />
              <q-input v-model="form.ean" label="EAN" outlined dense class="col-6" />
            </div>
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.base_price"
                label="Prix de vente"
                type="number"
                step="1"
                min="0"
                outlined
                dense
                class="col-6"
              />
              <q-input
                v-model="form.cost_amount"
                label="Coût"
                type="number"
                step="1"
                min="0"
                outlined
                dense
                class="col-6"
              />
            </div>
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.supplier_quantity"
                label="Stock fournisseur"
                type="number"
                step="1"
                min="0"
                outlined
                dense
                class="col-6"
              />
              <q-input
                v-model="form.local_quantity"
                label="Stock entrepôt"
                hint="Enregistré par un ajustement d'inventaire tracé"
                type="number"
                step="1"
                min="0"
                outlined
                dense
                class="col-6"
              />
            </div>
            <div class="row q-col-gutter-sm">
              <q-input v-model="form.image_url" label="URL image" outlined dense class="col-8" />
              <q-input
                v-model.number="form.weight"
                label="Poids (kg)"
                type="number"
                step="0.001"
                outlined
                dense
                class="col-4"
              />
            </div>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="editing ? 'Enregistrer' : 'Créer'"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { createVariant, deactivateVariant, listVariants, updateVariant } from '@/api/variants';
import { adjustInventory } from '@/api/inventory';
import { extractApiError } from '@/api/errors';
import type { ProductPublic } from '@/stores/products';
import { useShopConfigStore } from '@/stores/shopConfig';

const props = defineProps<{ productId: string }>();
const emit = defineEmits<{ changed: [] }>();

const shopConfig = useShopConfigStore();
const variants = ref<ProductPublic[]>([]);
const axes = ref<string[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const busyId = ref<string | null>(null);

function money(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toLocaleString('fr-FR')} ${shopConfig.currency}` : '—';
}
function qty(value: unknown): string {
  const n = Number(value);
  return Number.isFinite(n) ? String(Math.round(n)) : '0';
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const res = await listVariants(props.productId);
    variants.value = res.variants;
    axes.value = res.axes;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement des variantes impossible.';
  } finally {
    loading.value = false;
  }
}

// --- dialog ------------------------------------------------------------
const dialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editing = ref<ProductPublic | null>(null);
const optionRows = ref<{ name: string; value: string }[]>([]);
const form = reactive({
  name: '',
  supplier_sku: '',
  ean: '',
  base_price: '',
  cost_amount: '',
  supplier_quantity: '0',
  local_quantity: '0',
  image_url: '',
  weight: null as number | null,
});
let originalLocal = '0';

function str(v: unknown): string {
  if (v == null) return '';
  return typeof v === 'number' ? String(v) : typeof v === 'string' ? v : '';
}

function openCreate() {
  editing.value = null;
  dialogError.value = null;
  optionRows.value = axes.value.length
    ? axes.value.map((name) => ({ name, value: '' }))
    : [{ name: 'Taille', value: '' }];
  Object.assign(form, {
    name: '',
    supplier_sku: '',
    ean: '',
    base_price: '',
    cost_amount: '',
    supplier_quantity: '0',
    local_quantity: '0',
    image_url: '',
    weight: null,
  });
  originalLocal = '0';
  dialog.value = true;
}

function openEdit(variant: ProductPublic) {
  editing.value = variant;
  dialogError.value = null;
  optionRows.value = Object.entries(variant.variant_options ?? {}).map(([name, value]) => ({
    name,
    value,
  }));
  const rec = variant as unknown as Record<string, unknown>;
  Object.assign(form, {
    name: str(rec.name),
    supplier_sku: str(rec.supplier_sku),
    ean: str(rec.ean),
    base_price: str(rec.base_price),
    cost_amount: str(rec.cost_amount),
    supplier_quantity: qty(rec.supplier_quantity),
    local_quantity: qty(rec.local_quantity),
    image_url: str(rec.image_url),
    weight: rec.weight == null ? null : Number(rec.weight),
  });
  originalLocal = form.local_quantity;
  dialog.value = true;
}

function optionsPayload(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const row of optionRows.value) {
    const name = row.name.trim();
    const value = row.value.trim();
    if (name && value) out[name] = value;
  }
  return out;
}

async function saveLocalStock(variantId: string) {
  const next = qty(form.local_quantity);
  if (next === originalLocal) return;
  await adjustInventory({
    product_id: variantId,
    place_id: null,
    quantity: next,
    reason: editing.value ? 'Modification de la variante' : 'Stock initial de la variante',
  });
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  const options = optionsPayload();
  if (!Object.keys(options).length) {
    dialogError.value = 'Indiquez au moins une option (nom et valeur).';
    saving.value = false;
    return;
  }
  try {
    let saved: ProductPublic;
    if (editing.value) {
      saved = await updateVariant(editing.value.id, {
        variant_options: options,
        name: form.name.trim() || undefined,
        supplier_sku: form.supplier_sku.trim() || null,
        ean: form.ean.trim() || null,
        base_price: form.base_price.trim() || '0.00',
        cost_amount: form.cost_amount.trim() || '0.00',
        supplier_quantity: form.supplier_quantity.trim() || '0',
        image_url: form.image_url.trim() || null,
        weight: form.weight,
      });
    } else {
      saved = await createVariant(props.productId, {
        options,
        name: form.name.trim() || null,
        supplier_sku: form.supplier_sku.trim() || null,
        ean: form.ean.trim() || null,
        base_price: form.base_price.trim() || null,
        cost_amount: form.cost_amount.trim() || null,
        supplier_quantity: form.supplier_quantity.trim() || null,
        image_url: form.image_url.trim() || null,
        weight: form.weight,
      });
    }
    await saveLocalStock(saved.id);
    dialog.value = false;
    await load();
    emit('changed');
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function onDeactivate(variant: ProductPublic) {
  busyId.value = variant.id;
  error.value = null;
  try {
    await deactivateVariant(props.productId, variant.id);
    await load();
    emit('changed');
  } catch (err) {
    error.value = extractApiError(err) ?? 'Retrait impossible.';
  } finally {
    busyId.value = null;
  }
}

watch(
  () => props.productId,
  () => void load(),
);
onMounted(() => {
  void shopConfig.load();
  void load();
});
</script>
