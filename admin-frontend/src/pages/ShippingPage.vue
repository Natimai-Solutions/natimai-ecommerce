<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Logistique</div>
      <q-toggle
        v-model="showCompleted"
        label="Afficher les terminés"
        dense
        class="q-mr-md"
      />
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{
      notice
    }}</q-banner>

    <!-- Colis à grouper / traiter -->
    <div class="text-subtitle1 text-weight-medium q-mb-sm">Colis à grouper / traiter</div>
    <div class="text-caption text-grey-7 q-mb-sm">
      Tronçons d'acheminement non encore regroupés. Sélectionnez-en pour créer une consolidation, ou
      traitez-les individuellement.
    </div>

    <div v-if="selected.length" class="q-mb-sm">
      <q-btn
        color="primary"
        icon="inventory_2"
        :label="`Créer une consolidation (${selected.length})`"
        no-caps
        @click="openCreate"
      />
    </div>

    <q-table
      v-model:selected="selected"
      :rows="visiblePending"
      :columns="pendingColumns"
      row-key="tracking_id"
      selection="multiple"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
      :loading="loading"
    >
      <template #body-cell-order="props">
        <q-td :props="props">
          <q-btn
            flat
            dense
            no-caps
            color="primary"
            :label="`#${props.row.order_id.slice(0, 8)}`"
            :to="`/orders/${props.row.order_id}`"
          />
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            color="grey-7"
            text-color="white"
            :label="props.row.status_name || props.row.status_code || '—'"
          />
        </q-td>
      </template>
      <template #body-cell-ref="props">
        <q-td :props="props">{{ props.row.tracking_ref || '—' }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="timeline"
            color="grey-8"
            label="Parcours"
            @click="openJourney(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="local_shipping"
            color="primary"
            label="Remettre au transporteur"
            :disable="isTerminal(props.row) || isShipped(props.row)"
            @click="openShipTracking(props.row)"
          >
            <q-tooltip max-width="320px">
              Marque ce tronçon comme remis au transporteur et enregistre le n° de
              suivi (notifie le client). Ne fait pas passer au tronçon suivant.
            </q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            no-caps
            icon="skip_next"
            color="indigo"
            label="Tronçon suivant"
            :disable="isTerminal(props.row) || props.row.is_final_leg"
            @click="advanceTrackingRow(props.row)"
          >
            <q-tooltip v-if="props.row.is_final_leg" max-width="280px">
              Dernier tronçon du parcours — confirmez la livraison avec « Livrer ».
            </q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            no-caps
            icon="task_alt"
            color="positive"
            label="Livrer"
            :disable="isTerminal(props.row) || !props.row.is_final_leg"
            @click="deliver(props.row)"
          >
            <q-tooltip v-if="!props.row.is_final_leg" max-width="280px">
              Réservé au dernier tronçon — faites d'abord progresser le colis avec
              « Tronçon suivant ».
            </q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun colis à traiter.</div>
      </template>
    </q-table>

    <!-- Consolidations -->
    <div class="text-subtitle1 text-weight-medium q-mt-lg q-mb-sm">Consolidations</div>
    <q-table
      :rows="visibleConsolidations"
      :columns="consolidationColumns"
      row-key="id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
      :loading="loading"
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            color="grey-7"
            text-color="white"
            :label="props.row.status_name || props.row.status_code || '—'"
          />
        </q-td>
      </template>
      <template #body-cell-ref="props">
        <q-td :props="props">{{ props.row.tracking_ref || '—' }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn
            flat
            dense
            no-caps
            icon="local_shipping"
            color="primary"
            label="Tout remettre au transporteur"
            :disable="isTerminal(props.row) || isShipped(props.row)"
            @click="openShipConsolidation(props.row)"
          >
            <q-tooltip max-width="320px">
              Marque tous les colis du lot comme remis au transporteur et enregistre
              le n° de suivi (notifie les clients). Ne fait pas passer au tronçon suivant.
            </q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            no-caps
            icon="skip_next"
            color="indigo"
            label="Tronçon suivant"
            :disable="isTerminal(props.row)"
            @click="advanceConsolidationRow(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            icon="task_alt"
            color="positive"
            label="Livrer"
            :disable="isTerminal(props.row)"
            @click="deliverConsolidationRow(props.row)"
          />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucune consolidation.</div>
      </template>
    </q-table>

    <!-- Ship dialog (tracking ref) -->
    <q-dialog v-model="shipDialog">
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">Remise au transporteur</q-card-section>
        <q-form @submit.prevent="submitShip">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <q-select
              v-model="shipCarrierId"
              :options="carrierOptions"
              label="Transporteur"
              outlined
              dense
              emit-value
              map-options
            />
            <q-input
              v-model="shipRef"
              label="Numéro de suivi (optionnel)"
              hint="Laisser vide si vous n'avez pas de numéro (suivi géré en interne)."
              outlined
              dense
              autofocus
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Remettre au transporteur" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Advance consolidation: keep or ungroup the lot -->
    <q-dialog v-model="ungroupDialog">
      <q-card style="min-width: 400px">
        <q-card-section class="text-h6">Passage au tronçon suivant</q-card-section>
        <q-card-section class="q-pt-none">
          <div class="text-body2 text-grey-8 q-mb-sm">
            Conserver le groupage pour le prochain tronçon, ou dégrouper les colis pour
            qu'ils continuent individuellement (livraisons séparées) ?
          </div>
          <q-option-group
            v-model="ungroupChoice"
            :options="[
              { label: 'Garder le groupage', value: 'keep' },
              { label: 'Dégrouper (colis individuels)', value: 'ungroup' },
            ]"
            color="primary"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Annuler" v-close-popup />
          <q-btn
            color="primary"
            label="Valider"
            :loading="ungroupBusy"
            @click="submitAdvanceConsolidation"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Journey dialog (parcours du colis) -->
    <q-dialog v-model="journeyDialog">
      <q-card style="min-width: 480px; max-width: 620px">
        <q-card-section class="text-h6">
          Parcours du colis
          <div class="text-caption text-grey-7">Commande #{{ journeyOrderId?.slice(0, 8) }}</div>
        </q-card-section>
        <q-card-section class="q-pt-none">
          <q-banner v-if="journeyError" class="bg-red-1 text-red-9" dense rounded>{{
            journeyError
          }}</q-banner>
          <div v-else-if="journeyLoading" class="text-center q-pa-md">
            <q-spinner size="2em" color="primary" />
          </div>
          <div v-else-if="journey.length === 0" class="text-grey-6 q-pa-md text-center">
            Aucun tronçon.
          </div>
          <q-timeline v-else color="primary" layout="comfortable">
            <q-timeline-entry
              v-for="leg in journey"
              :key="leg.tracking_id"
              :title="`Tronçon ${leg.sequence_order} — ${legPath(leg)}`"
              :subtitle="leg.route_name || ''"
              :icon="leg.is_current ? 'my_location' : 'place'"
              :color="legColor(leg)"
            >
              <div class="row items-center q-gutter-sm">
                <q-chip
                  dense
                  size="sm"
                  :color="legColor(leg)"
                  text-color="white"
                  :label="leg.status_name || leg.status_code || '—'"
                />
                <span v-if="leg.mode" class="text-caption text-grey-7">{{ leg.mode }}</span>
                <span v-if="leg.tracking_ref" class="text-caption"
                  >réf. {{ leg.tracking_ref }}</span
                >
                <q-badge v-if="leg.is_current" color="orange" label="en cours" />
              </div>
            </q-timeline-entry>
          </q-timeline>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Fermer" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Create consolidation dialog -->
    <q-dialog v-model="createDialog">
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">Nouvelle consolidation</q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <div class="text-caption text-grey-7">{{ selected.length }} colis sélectionné(s).</div>
            <q-input
              v-model="createName"
              label="Nom de la consolidation *"
              outlined
              dense
              autofocus
              :rules="[(v) => (!!v && v.trim().length > 0) || 'Nom requis']"
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Créer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import {
  addTrackings,
  advanceConsolidation,
  advanceTracking,
  createConsolidation,
  deliverConsolidation,
  deliverTracking,
  getOrderJourney,
  getUngroupHint,
  listCarriers,
  listConsolidations,
  listPendingGrouping,
  shipConsolidation,
  shipTracking,
  type Carrier,
  type Consolidation,
  type JourneyLeg,
  type PendingTracking,
} from '@/api/shipping';
import { extractApiError } from '@/api/errors';

const $q = useQuasar();

const pending = ref<PendingTracking[]>([]);
const consolidations = ref<Consolidation[]>([]);
const carriers = ref<Carrier[]>([]);
const selected = ref<PendingTracking[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);

const pendingColumns: QTableColumn[] = [
  { name: 'order', label: 'Commande', field: 'order_id', align: 'left' },
  {
    name: 'sequence',
    label: 'Tronçon',
    field: 'sequence_order',
    align: 'left',
    format: (v: number) => `Tronçon ${v}`,
  },
  { name: 'status', label: 'Statut', field: 'status_code', align: 'left' },
  { name: 'ref', label: 'Référence', field: 'tracking_ref', align: 'left' },
  { name: 'actions', label: '', field: 'tracking_id', align: 'right' },
];

const consolidationColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'code', label: 'Code', field: 'consolidation_code', align: 'left' },
  { name: 'status', label: 'Statut', field: 'status_code', align: 'left' },
  { name: 'total_orders', label: 'Colis', field: 'total_orders', align: 'left' },
  { name: 'ref', label: 'Référence', field: 'tracking_ref', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [pending.value, consolidations.value, carriers.value] = await Promise.all([
      listPendingGrouping(),
      listConsolidations(),
      listCarriers(),
    ]);
    selected.value = [];
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// --- Action gating (disable buttons once a leg is terminal/shipped) ---
const TERMINAL_STATUS_CODES = ['completed', 'delivered'];
function isTerminal(row: { status_code: string | null }): boolean {
  return TERMINAL_STATUS_CODES.includes(row.status_code ?? '');
}
function isShipped(row: { status_code: string | null }): boolean {
  return row.status_code === 'shipped';
}

// Les tronçons/lots terminés sont masqués par défaut (toggle pour l'historique).
const showCompleted = ref(false);
const visiblePending = computed(() =>
  showCompleted.value ? pending.value : pending.value.filter((r) => !isTerminal(r)),
);
const visibleConsolidations = computed(() =>
  showCompleted.value
    ? consolidations.value
    : consolidations.value.filter((c) => !isTerminal(c)),
);

// --- Ship (tracking or consolidation) ---
const shipDialog = ref(false);
const shipRef = ref('');
const shipCarrierId = ref<string | null>(null);
const shipTarget = ref<{ type: 'tracking' | 'consolidation'; id: string } | null>(null);

const carrierOptions = computed<{ label: string; value: string | null }[]>(() => [
  { label: '— Suivi interne (sans transporteur) —', value: null },
  ...carriers.value.map((c) => ({ label: c.name, value: c.id })),
]);

function openShipTracking(row: PendingTracking) {
  dialogError.value = null;
  shipRef.value = row.tracking_ref ?? '';
  shipCarrierId.value = null;
  shipTarget.value = { type: 'tracking', id: row.tracking_id };
  shipDialog.value = true;
}

function openShipConsolidation(c: Consolidation) {
  dialogError.value = null;
  shipRef.value = c.tracking_ref ?? '';
  shipCarrierId.value = null;
  shipTarget.value = { type: 'consolidation', id: c.id };
  shipDialog.value = true;
}

async function submitShip() {
  if (!shipTarget.value) return;
  // Carrier and reference are both optional (self-managed shipments).
  const ref = shipRef.value.trim() || null;
  const carrierId = shipCarrierId.value;
  saving.value = true;
  dialogError.value = null;
  try {
    if (shipTarget.value.type === 'tracking') {
      await shipTracking(shipTarget.value.id, ref, carrierId);
    } else {
      await shipConsolidation(shipTarget.value.id, ref, carrierId);
    }
    shipDialog.value = false;
    notice.value = 'Remise au transporteur enregistrée.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Expédition impossible.';
  } finally {
    saving.value = false;
  }
}

async function deliver(row: PendingTracking) {
  error.value = null;
  try {
    await deliverTracking(row.tracking_id);
    notice.value = 'Colis marqué livré.';
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  }
}

// --- Advance to next leg (tronçon suivant) ---
async function advanceTrackingRow(row: PendingTracking) {
  error.value = null;
  try {
    const res = await advanceTracking(row.tracking_id);
    notice.value = res.message;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  }
}

// --- Consolidation: advance (keep/ungroup popup) & deliver (forced ungroup) ---
const ungroupDialog = ref(false);
const ungroupTarget = ref<Consolidation | null>(null);
const ungroupChoice = ref<'keep' | 'ungroup'>('keep');
const ungroupBusy = ref(false);

async function advanceConsolidationRow(c: Consolidation) {
  ungroupTarget.value = c;
  ungroupChoice.value = 'keep';
  ungroupDialog.value = true;
  // Smart default: pre-select "Dégrouper" when the next leg is the last-leg or
  // the parcels diverge onto different legs.
  try {
    if (await getUngroupHint(c.id)) ungroupChoice.value = 'ungroup';
  } catch {
    // keep the default on error
  }
}

async function submitAdvanceConsolidation() {
  if (!ungroupTarget.value) return;
  ungroupBusy.value = true;
  error.value = null;
  try {
    const res = await advanceConsolidation(
      ungroupTarget.value.id,
      ungroupChoice.value === 'ungroup',
    );
    notice.value = res.message;
    ungroupDialog.value = false;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  } finally {
    ungroupBusy.value = false;
  }
}

function deliverConsolidationRow(c: Consolidation) {
  $q.dialog({
    title: 'Livrer le lot',
    message: 'Chaque colis sera dégroupé et marqué « livré ». Continuer ?',
    cancel: true,
    ok: { label: 'Livrer', color: 'positive' },
  }).onOk(() => {
    void (async () => {
      error.value = null;
      try {
        const res = await deliverConsolidation(c.id);
        notice.value = res.message;
        await load();
      } catch (err) {
        error.value = extractApiError(err) ?? 'Opération impossible.';
      }
    })();
  });
}

// --- Journey (parcours du colis) ---
const journeyDialog = ref(false);
const journey = ref<JourneyLeg[]>([]);
const journeyLoading = ref(false);
const journeyError = ref<string | null>(null);
const journeyOrderId = ref<string | null>(null);

const _legColors: Record<string, string> = {
  delivered: 'green',
  completed: 'teal',
  shipped: 'indigo',
  in_progress: 'blue',
  pending: 'grey',
};
function legColor(leg: JourneyLeg): string {
  return _legColors[leg.status_code ?? ''] ?? 'grey-7';
}
function legPath(leg: JourneyLeg): string {
  return `${leg.from_place ?? '?'} → ${leg.to_place ?? '?'}`;
}

async function openJourney(row: PendingTracking) {
  journeyOrderId.value = row.order_id;
  journey.value = [];
  journeyError.value = null;
  journeyLoading.value = true;
  journeyDialog.value = true;
  try {
    journey.value = await getOrderJourney(row.order_id);
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Chargement du parcours impossible.';
  } finally {
    journeyLoading.value = false;
  }
}

// --- Create consolidation from selection ---
const createDialog = ref(false);
const createName = ref('');

function openCreate() {
  dialogError.value = null;
  createName.value = '';
  createDialog.value = true;
}

async function submitCreate() {
  if (!createName.value.trim() || selected.value.length === 0) return;
  // A consolidation groups trackings of a single route.
  const routeIds = new Set(selected.value.map((t) => t.route_id));
  if (routeIds.size > 1) {
    dialogError.value = 'Les colis sélectionnés doivent appartenir au même tronçon (route).';
    return;
  }
  const first = selected.value[0];
  if (!first) return;
  saving.value = true;
  dialogError.value = null;
  try {
    const consolidation = await createConsolidation({
      route_id: first.route_id,
      name: createName.value.trim(),
    });
    await addTrackings(
      consolidation.id,
      selected.value.map((t) => t.tracking_id),
    );
    createDialog.value = false;
    notice.value = 'Consolidation créée.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Création impossible.';
  } finally {
    saving.value = false;
  }
}

void load();
</script>
