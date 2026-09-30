<template>
  <q-page class="admin-page">
    <PageHeader title="Douane par catégorie">
      <template #hint>
        Taux effectif de l'ensemble des droits et taxes à l'import, appliqué sur la valeur CAF (voir
        DEPLOYMENT.md §15). Un produit dont le taux ne se résout ni sur lui-même ni sur sa catégorie
        est masqué de la vitrine.
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
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="report" class="customs-kpis">
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">Publiables</span>
        <span class="customs-kpi__value font-mono"
          >{{ report.publishable_count }} / {{ report.enriched_count }}</span
        >
        <span class="customs-kpi__hint">produits enrichis</span>
      </div>
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">Sans taux de douane</span>
        <span
          class="customs-kpi__value font-mono"
          :class="report.blocked_customs_rate_unresolved ? 'text-negative' : 'text-positive'"
        >
          {{ report.blocked_customs_rate_unresolved }}
        </span>
        <span class="customs-kpi__hint">à traiter ci-dessous</span>
      </div>
      <div class="app-panel customs-kpi">
        <span class="customs-kpi__label">Sans poids</span>
        <span
          class="customs-kpi__value font-mono"
          :class="report.blocked_weight_missing ? 'text-negative' : 'text-positive'"
        >
          {{ report.blocked_weight_missing }}
        </span>
        <span class="customs-kpi__hint">fret incalculable — fiche produit</span>
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
          <span v-else class="text-subtle text-italic">Sans catégorie</span>
        </q-td>
      </template>
      <template #body-cell-rate="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct" class="font-mono"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <StatusTag v-else label="Non défini" tone="danger" icon="ph:warning-circle" />
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
            <q-tooltip>Définir le taux de douane</q-tooltip>
          </q-btn>
          <q-tooltip v-else>
            Ces produits n'ont pas de catégorie : leur taux ne peut pas être hérité.
          </q-tooltip>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucune catégorie.</div>
      </template>
    </q-table>

    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ editing?.category_name ?? 'Catégorie' }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="editRate"
              label="Taux de douane (%)"
              hint="Vide = aucun taux : les produits de cette catégorie restent masqués"
              type="number"
              step="0.01"
              outlined
              dense
            />
            <p class="admin-hint q-mb-none">
              Saisir le <strong>taux effectif</strong> : l'ensemble des droits et taxes à l'import
              (droits de douane, TDL et les autres prélèvements de la position tarifaire) ramené à
              un seul pourcentage de la valeur CAF — pas le seul droit de douane. Le dériver du
              <a
                href="https://simulateur-douane-polynesie.com/"
                target="_blank"
                rel="noopener"
                class="admin-link"
                >simulateur des douanes PF</a
              >
              en simulant une valeur représentative, origine UE pour le corridor France → Papeete.
            </p>
            <AppNotice tone="warning" dense>
              <strong>Retirer la TVA du total du simulateur.</strong> Elle est déjà appliquée
              séparément via le taux de TVA du produit : l'inclure ici la compterait deux fois sur
              chaque prix.
            </AppNotice>
            <p class="admin-hint q-mb-none">
              Procédure complète, règle en cas de positions multiples et tableau de suivi :
              <code>DEPLOYMENT.md</code> §15.
            </p>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
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
import { onMounted, ref } from 'vue';
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
import { extractApiError } from '@/api/errors';

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
