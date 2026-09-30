<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="col">
        <div class="text-h6">Catégories</div>
        <div class="text-caption text-grey-7">
          Les catégories viennent de la synchronisation fournisseur : leur nom d'origine sert de clé
          de rapprochement et ne se modifie pas. Personnalisez le titre vitrine, la description et
          l'image ; fusionnez les doublons. Taux de TVA et de douane : pages dédiées.
        </div>
      </div>
      <q-toggle v-model="showMerged" label="Afficher les fusionnées" class="q-mr-md" />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>
      {{ notice }}
    </q-banner>

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
          <div v-if="props.row.display_name" class="text-caption text-grey-7">
            Nom fournisseur : {{ props.row.name }}
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            v-if="props.row.merged_into_id"
            dense
            color="grey-6"
            text-color="white"
            icon="merge"
            :label="`Fusionnée dans ${props.row.merged_into_name ?? '?'}`"
          />
          <q-chip
            v-else
            dense
            :color="props.row.is_active ? 'green' : 'grey-6'"
            text-color="white"
            :label="props.row.is_active ? 'Active' : 'Inactive'"
          />
        </q-td>
      </template>
      <template #body-cell-customs="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <span v-else class="text-grey-6">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <template v-if="!props.row.merged_into_id">
            <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)">
              <q-tooltip>Titre vitrine, description, image</q-tooltip>
            </q-btn>
            <q-btn flat dense icon="merge" color="secondary" @click="openMerge(props.row)">
              <q-tooltip>Fusionner dans une autre catégorie</q-tooltip>
            </q-btn>
            <q-btn
              flat
              dense
              :icon="props.row.is_active ? 'visibility_off' : 'visibility'"
              :color="props.row.is_active ? 'negative' : 'positive'"
              :loading="busyIds.has(props.row.id)"
              @click="onToggleActive(props.row)"
            >
              <q-tooltip>{{ props.row.is_active ? 'Désactiver' : 'Réactiver' }}</q-tooltip>
            </q-btn>
          </template>
        </q-td>
      </template>
    </q-table>

    <div class="text-caption text-grey-7 q-mt-sm">{{ visibleRows.length }} catégorie(s)</div>

    <!-- Édition -->
    <q-dialog v-model="editDialog">
      <q-card style="min-width: 460px">
        <q-card-section class="text-h6">{{ editing?.name }}</q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
                  icon="photo_library"
                  label="Médiathèque"
                  @click="mediaPickerOpen = true"
                />
              </template>
            </q-input>
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
            <div class="text-caption text-grey-7">
              Ces champs ne sont jamais réécrits par la synchronisation.
            </div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Fusion -->
    <q-dialog v-model="mergeDialog">
      <q-card style="min-width: 460px">
        <q-card-section class="text-h6">Fusionner « {{ merging?.title }} »</q-card-section>
        <q-form @submit.prevent="submitMerge">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
            <q-banner dense class="bg-orange-1 text-grey-9" rounded>
              <template #avatar><q-icon name="warning" color="orange-8" /></template>
              <span class="text-caption">
                Les {{ merging?.product_count ?? 0 }} produit(s) et les remises de cette catégorie
                passent sur la cible. La catégorie devient inactive mais reste connue : la prochaine
                synchronisation continuera d'envoyer ses produits vers la cible.
                <strong>Irréversible.</strong>
              </span>
            </q-banner>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="negative"
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
import MediaPicker from '@/components/MediaPicker.vue';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  listAdminCategories,
  mergeCategory,
  updateAdminCategory,
  type AdminCategory,
} from '@/api/categories';
import { extractApiError } from '@/api/errors';

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
  { name: 'product_count', label: 'Produits', field: 'product_count', align: 'right' },
  { name: 'customs', label: 'Douane', field: 'default_customs_rate_pct', align: 'left' },
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
}>({
  display_name: '',
  description: '',
  image_url: '',
  default_margin_rate_pct: '',
});

function openEdit(category: AdminCategory) {
  dialogError.value = null;
  editing.value = category;
  editForm.display_name = category.display_name ?? '';
  editForm.description = category.description ?? '';
  editForm.image_url = category.image_url ?? '';
  editForm.default_margin_rate_pct = category.default_margin_rate_pct ?? '';
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

onMounted(load);
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
