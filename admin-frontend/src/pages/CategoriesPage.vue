<template>
  <q-page class="admin-page">
    <PageHeader title="Catégories">
      <template #hint>
        Les catégories viennent de la synchronisation fournisseur : leur nom d'origine sert de clé
        de rapprochement et ne se modifie pas. Personnalisez le titre vitrine, la description,
        l'image, la marge et le taux de TVA par défaut ; fusionnez les doublons.
      </template>
      <template #actions>
        <q-toggle v-model="showMerged" label="Afficher les fusionnées" />
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <q-table
      :rows="visibleRows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-title="props">
        <q-td :props="props">
          <div class="text-body2">{{ props.row.title }}</div>
          <div v-if="props.row.display_name" class="text-caption text-muted">
            Nom fournisseur : {{ props.row.name }}
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            v-if="props.row.merged_into_id"
            tone="neutral"
            icon="ph:git-merge"
            :label="`Fusionnée dans ${props.row.merged_into_name ?? '?'}`"
          />
          <StatusTag
            v-else-if="props.row.is_active"
            tone="ok"
            icon="ph:check-circle"
            label="Active"
          />
          <StatusTag v-else tone="neutral" icon="ph:minus-circle" label="Inactive" />
        </q-td>
      </template>
      <template #body-cell-customs="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct" class="font-mono"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <template v-if="!props.row.merged_into_id">
            <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
              <q-tooltip>Titre vitrine, description, image</q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:git-merge" @click="openMerge(props.row)">
              <q-tooltip>Fusionner dans une autre catégorie</q-tooltip>
            </q-btn>
            <q-btn
              flat
              round
              dense
              :icon="props.row.is_active ? 'ph:eye-slash' : 'ph:eye'"
              :color="props.row.is_active ? 'negative' : undefined"
              :loading="busyIds.has(props.row.id)"
              @click="onToggleActive(props.row)"
            >
              <q-tooltip>{{ props.row.is_active ? 'Désactiver' : 'Réactiver' }}</q-tooltip>
            </q-btn>
          </template>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucune catégorie.</div>
      </template>
    </q-table>

    <div class="text-caption text-muted q-mt-sm">{{ visibleRows.length }} catégorie(s)</div>

    <!-- Édition -->
    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ editing?.name }}</h2>
          <p class="app-dialog__text">Ces champs ne sont jamais réécrits par la synchronisation.</p>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="editForm.display_name"
              label="Titre vitrine"
              :hint="`Vide = « ${editing?.name ?? ''} » (nom fournisseur)`"
              outlined
              dense
              clearable
            />
            <q-input
              v-model="editForm.description"
              label="Description"
              type="textarea"
              autogrow
              outlined
              dense
            />
            <q-input
              v-model="editForm.image_url"
              label="Image de la tuile vitrine"
              hint="Affichée sur l'accueil ; médiathèque ou URL"
              outlined
              dense
            >
              <template v-if="editForm.image_url" #prepend>
                <img :src="editForm.image_url" alt="" class="image-field__thumb" />
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
            <q-select
              v-model="editForm.default_tax_rate_id"
              :options="taxRateOptions"
              label="Taux de TVA par défaut"
              hint="Vide = taux par défaut de la boutique ; un article peut le surcharger"
              outlined
              dense
              emit-value
              map-options
              clearable
              data-testid="category-tax-rate"
            />
            <q-input
              v-model="editForm.default_margin_rate_pct"
              label="Marge par défaut (%)"
              hint="Vide = marge du groupe tarifaire du client ; un article peut la surcharger"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Fusion -->
    <q-dialog v-model="mergeDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Fusionner « {{ merging?.title }} »</h2>
        </q-card-section>
        <q-form @submit.prevent="submitMerge">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-select
              v-model="mergeTarget"
              :options="mergeTargets"
              label="Catégorie cible *"
              outlined
              dense
              emit-value
              map-options
              use-input
              input-debounce="0"
              @filter="filterTargets"
            />
            <AppNotice tone="warning" dense>
              Les {{ merging?.product_count ?? 0 }} produit(s) et les remises de cette catégorie
              passent sur la cible. La catégorie devient inactive mais reste connue : la prochaine
              synchronisation continuera d'envoyer ses produits vers la cible.
              <strong>Irréversible.</strong>
            </AppNotice>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="negative"
              unelevated
              no-caps
              label="Fusionner"
              :loading="saving"
              :disable="!mergeTarget"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
    <MediaPicker
      v-model="mediaPickerOpen"
      kind="category"
      @select="(asset) => (editForm.image_url = asset.url)"
    />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  listAdminCategories,
  mergeCategory,
  updateAdminCategory,
  type AdminCategory,
} from '@/api/categories';
import { extractApiError } from '@/api/errors';
import { listTaxRates, setCategoryTaxRate, type TaxRate } from '@/api/taxRates';

const rows = ref<AdminCategory[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const showMerged = ref(false);

const visibleRows = computed(() =>
  showMerged.value ? rows.value : rows.value.filter((c) => !c.merged_into_id),
);

const columns: QTableColumn[] = [
  { name: 'title', label: 'Catégorie', field: 'title', align: 'left' },
  { name: 'status', label: 'Statut', field: 'is_active', align: 'left' },
  {
    name: 'product_count',
    label: 'Produits',
    field: 'product_count',
    align: 'right',
    classes: 'font-mono',
  },
  { name: 'customs', label: 'Douane', field: 'default_customs_rate_pct', align: 'left' },
  {
    name: 'tax',
    label: 'TVA',
    field: (r) => taxLabel(r.default_tax_rate_id),
    align: 'left',
  },
  {
    name: 'margin',
    label: 'Marge',
    field: (r) => (r.default_margin_rate_pct ? `${r.default_margin_rate_pct} %` : '—'),
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listAdminCategories();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// Activation
const busyIds = ref(new Set<string>());

async function onToggleActive(category: AdminCategory) {
  notice.value = null;
  error.value = null;
  busyIds.value = new Set(busyIds.value).add(category.id);
  try {
    await updateAdminCategory(category.id, { is_active: !category.is_active });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Modification impossible.';
  } finally {
    const next = new Set(busyIds.value);
    next.delete(category.id);
    busyIds.value = next;
  }
}

// Édition
const editDialog = ref(false);
const editing = ref<AdminCategory | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editForm = reactive<{
  display_name: string | null;
  description: string;
  image_url: string;
  default_margin_rate_pct: string;
  default_tax_rate_id: string | null;
}>({
  display_name: '',
  description: '',
  image_url: '',
  default_margin_rate_pct: '',
  default_tax_rate_id: null,
});

// Taux de TVA en vigueur, pour le taux par défaut d'une catégorie.
const taxRates = ref<TaxRate[]>([]);
const taxRateOptions = computed(() =>
  taxRates.value.map((rate) => ({
    value: rate.id,
    label: `${rate.label} — ${Number(rate.rate_pct).toLocaleString('fr-FR')} %`,
  })),
);

function taxLabel(taxRateId: string | null | undefined): string {
  if (!taxRateId) return '—';
  const rate = taxRates.value.find((r) => r.id === taxRateId);
  return rate ? `${Number(rate.rate_pct).toLocaleString('fr-FR')} %` : '—';
}

async function loadTaxRates() {
  try {
    taxRates.value = await listTaxRates({ valid: true });
  } catch {
    // Non bloquant : le sélecteur reste vide.
  }
}

function openEdit(category: AdminCategory) {
  dialogError.value = null;
  editing.value = category;
  editForm.display_name = category.display_name ?? '';
  editForm.description = category.description ?? '';
  editForm.image_url = category.image_url ?? '';
  editForm.default_margin_rate_pct = category.default_margin_rate_pct ?? '';
  editForm.default_tax_rate_id = category.default_tax_rate_id ?? null;
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await updateAdminCategory(editing.value.id, {
      display_name: (editForm.display_name ?? '').trim() || null,
      description: editForm.description.trim() || null,
      image_url: editForm.image_url.trim() || null,
      default_margin_rate_pct: String(editForm.default_margin_rate_pct ?? '').trim() || null,
    });
    if ((editing.value.default_tax_rate_id ?? null) !== editForm.default_tax_rate_id) {
      await setCategoryTaxRate(editing.value.id, editForm.default_tax_rate_id);
    }
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

// Fusion
const mergeDialog = ref(false);
const merging = ref<AdminCategory | null>(null);
const mergeTarget = ref<string | null>(null);
const mergeTargets = ref<{ label: string; value: string }[]>([]);

function allTargets(): { label: string; value: string }[] {
  return rows.value
    .filter((c) => c.is_active && !c.merged_into_id && c.id !== merging.value?.id)
    .map((c) => ({ label: `${c.title} (${c.product_count})`, value: c.id }));
}

function filterTargets(needle: string, update: (fn: () => void) => void) {
  update(() => {
    const q = needle.trim().toLowerCase();
    mergeTargets.value = allTargets().filter((o) => !q || o.label.toLowerCase().includes(q));
  });
}

function openMerge(category: AdminCategory) {
  dialogError.value = null;
  merging.value = category;
  mergeTarget.value = null;
  mergeTargets.value = allTargets();
  mergeDialog.value = true;
}

async function submitMerge() {
  if (!merging.value || !mergeTarget.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    const result = await mergeCategory(merging.value.id, mergeTarget.value);
    mergeDialog.value = false;
    notice.value = `« ${result.source.title} » fusionnée dans « ${result.target.title} » : ${result.moved_products} produit(s) et ${result.moved_discounts} remise(s) déplacés.`;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Fusion impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadTaxRates();
});
const mediaPickerOpen = ref(false);
</script>

<style scoped lang="scss">
.image-field__thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
</style>
