<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="col">
        <div class="text-h6">Douane par catégorie</div>
        <div class="text-caption text-grey-7">
          Taux effectif de l'ensemble des droits et taxes à l'import, appliqué sur la valeur CAF
          (voir DEPLOYMENT.md §15). Un produit dont le taux ne se résout ni sur lui-même ni sur sa
          catégorie est masqué de la vitrine.
        </div>
      </div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="report" class="row q-col-gutter-md q-mb-md">
      <div class="col-12 col-sm-4">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-caption text-grey-7">Publiables</div>
            <div class="text-h5">{{ report.publishable_count }} / {{ report.enriched_count }}</div>
            <div class="text-caption text-grey-7">produits enrichis</div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-sm-4">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-caption text-grey-7">Sans taux de douane</div>
            <div
              class="text-h5"
              :class="report.blocked_customs_rate_unresolved ? 'text-negative' : 'text-positive'"
            >
              {{ report.blocked_customs_rate_unresolved }}
            </div>
            <div class="text-caption text-grey-7">à traiter ci-dessous</div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-sm-4">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-caption text-grey-7">Sans poids</div>
            <div
              class="text-h5"
              :class="report.blocked_weight_missing ? 'text-negative' : 'text-positive'"
            >
              {{ report.blocked_weight_missing }}
            </div>
            <div class="text-caption text-grey-7">fret incalculable — fiche produit</div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-table
      :rows="report?.categories ?? []"
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
          <span v-else class="text-grey-6 text-italic">Sans catégorie</span>
        </q-td>
      </template>
      <template #body-cell-rate="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <q-chip v-else dense color="negative" text-color="white" label="Non défini" />
        </q-td>
      </template>
      <template #body-cell-blocked="props">
        <q-td :props="props">
          <q-chip
            dense
            :color="props.row.blocked_count ? 'negative' : 'green'"
            text-color="white"
            :label="String(props.row.blocked_count)"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            v-if="props.row.category_id"
            flat
            dense
            icon="edit"
            color="primary"
            @click="openEdit(props.row)"
          >
            <q-tooltip>Définir le taux de douane</q-tooltip>
          </q-btn>
          <q-tooltip v-else>
            Ces produits n'ont pas de catégorie : leur taux ne peut pas être hérité.
          </q-tooltip>
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card style="min-width: 380px">
        <q-card-section class="text-h6">
          {{ editing?.category_name ?? 'Catégorie' }}
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <q-input
              v-model="editRate"
              label="Taux de douane (%)"
              hint="Vide = aucun taux : les produits de cette catégorie restent masqués"
              type="number"
              step="0.01"
              outlined
              dense
            />
            <div class="text-caption text-grey-7">
              Saisir le <strong>taux effectif</strong> : l'ensemble des droits et taxes à l'import
              (droits de douane, TDL et les autres prélèvements de la position tarifaire) ramené à
              un seul pourcentage de la valeur CAF — pas le seul droit de douane. Le dériver du
              <a href="https://simulateur-douane-polynesie.com/" target="_blank" rel="noopener"
                >simulateur des douanes PF</a
              >
              en simulant une valeur représentative, origine UE pour le corridor France → Papeete.
            </div>
            <q-banner dense class="bg-orange-1 text-grey-9" rounded>
              <template #avatar><q-icon name="warning" color="orange-8" /></template>
              <span class="text-caption">
                <strong>Retirer la TVA du total du simulateur.</strong> Elle est déjà appliquée
                séparément via le taux TVA/TGC du produit : l'inclure ici la compterait deux fois
                sur chaque prix.
              </span>
            </q-banner>
            <div class="text-caption text-grey-7">
              Procédure complète, règle en cas de positions multiples et tableau de suivi :
              <code>DEPLOYMENT.md</code> §15.
            </div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn color="primary" label="Enregistrer" type="submit" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import {
  getPublicationReport,
  setCategoryCustomsRate,
  type CategoryPublicationRow,
  type PublicationReport,
} from 'src/api/taxRates';
import { extractApiError } from 'src/api/errors';

const report = ref<PublicationReport | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const columns: QTableColumn[] = [
  { name: 'category_name', label: 'Catégorie', field: 'category_name', align: 'left' },
  { name: 'rate', label: 'Douane', field: 'default_customs_rate_pct', align: 'left' },
  { name: 'product_count', label: 'Produits', field: 'product_count', align: 'right' },
  { name: 'blocked', label: 'Masqués', field: 'blocked_count', align: 'left' },
  { name: 'actions', label: '', field: 'category_id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    report.value = await getPublicationReport();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
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
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
