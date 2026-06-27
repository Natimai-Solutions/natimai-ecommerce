<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Logistique</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{ notice }}</q-banner>

    <!-- Colis à grouper / traiter -->
    <div class="text-subtitle1 text-weight-medium q-mb-sm">Colis à grouper / traiter</div>
    <div class="text-caption text-grey-7 q-mb-sm">
      Tronçons d'acheminement non encore regroupés. Sélectionnez-en pour créer une consolidation,
      ou traitez-les individuellement.
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
      :rows="pending"
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
          <q-chip dense size="sm" color="grey-7" text-color="white" :label="props.row.status_name || props.row.status_code || '—'" />
        </q-td>
      </template>
      <template #body-cell-ref="props">
        <q-td :props="props">{{ props.row.tracking_ref || '—' }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense no-caps icon="timeline" color="grey-8" label="Parcours" @click="openJourney(props.row)" />
          <q-btn flat dense no-caps icon="local_shipping" color="primary" label="Expédier" @click="openShipTracking(props.row)" />
          <q-btn flat dense no-caps icon="skip_next" color="indigo" label="Tronçon suivant" @click="advanceTrackingRow(props.row)" />
          <q-btn flat dense no-caps icon="task_alt" color="positive" label="Livrer" @click="deliver(props.row)" />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun colis à traiter.</div>
      </template>
    </q-table>

    <!-- Consolidations -->
    <div class="text-subtitle1 text-weight-medium q-mt-lg q-mb-sm">Consolidations</div>
    <q-table
      :rows="consolidations"
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
          <q-chip dense size="sm" color="grey-7" text-color="white" :label="props.row.status_name || props.row.status_code || '—'" />
        </q-td>
      </template>
      <template #body-cell-ref="props">
        <q-td :props="props">{{ props.row.tracking_ref || '—' }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense no-caps icon="local_shipping" color="primary" label="Expédier tout" @click="openShipConsolidation(props.row)" />
          <q-btn flat dense no-caps icon="skip_next" color="indigo" label="Tronçon suivant" @click="advanceConsolidationRow(props.row)" />
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucune consolidation.</div>
      </template>
    </q-table>

    <!-- Ship dialog (tracking ref) -->
    <q-dialog v-model="shipDialog">
      <q-card style="min-width: 360px">
        <q-card-section class="text-h6">Référence d'expédition</q-card-section>
        <q-form @submit.prevent="submitShip">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{ dialogError }}</q-banner>
            <q-input
              v-model="shipRef"
              label="Référence transporteur *"
              outlined
              dense
              autofocus
              :rules="[(v) => (!!v && v.trim().length > 0) || 'Référence requise']"
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Expédier" :loading="saving" />
          </q-card-actions>
        </q-form>
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
          <q-banner v-if="journeyError" class="bg-red-1 text-red-9" dense rounded>{{ journeyError }}</q-banner>
          <div v-else-if="journeyLoading" class="text-center q-pa-md"><q-spinner size="2em" color="primary" /></div>
          <div v-else-if="journey.length === 0" class="text-grey-6 q-pa-md text-center">Aucun tronçon.</div>
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
                <q-chip dense size="sm" :color="legColor(leg)" text-color="white" :label="leg.status_name || leg.status_code || '—'" />
                <span v-if="leg.mode" class="text-caption text-grey-7">{{ leg.mode }}</span>
                <span v-if="leg.tracking_ref" class="text-caption">réf. {{ leg.tracking_ref }}</span>
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
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{ dialogError }}</q-banner>
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
import { ref } from 'vue'
import type { QTableColumn } from 'quasar'
import {
  addTrackings,
  advanceConsolidation,
  advanceTracking,
  createConsolidation,
  deliverTracking,
  getOrderJourney,
  listConsolidations,
  listPendingGrouping,
  shipConsolidation,
  shipTracking,
  type Consolidation,
  type JourneyLeg,
  type PendingTracking,
} from 'src/api/shipping'
import { extractApiError } from 'src/api/errors'

const pending = ref<PendingTracking[]>([])
const consolidations = ref<Consolidation[]>([])
const selected = ref<PendingTracking[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const saving = ref(false)
const dialogError = ref<string | null>(null)

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
]

const consolidationColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'code', label: 'Code', field: 'consolidation_code', align: 'left' },
  { name: 'status', label: 'Statut', field: 'status_code', align: 'left' },
  { name: 'total_orders', label: 'Colis', field: 'total_orders', align: 'left' },
  { name: 'ref', label: 'Référence', field: 'tracking_ref', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]

async function load() {
  loading.value = true
  error.value = null
  try {
    ;[pending.value, consolidations.value] = await Promise.all([
      listPendingGrouping(),
      listConsolidations(),
    ])
    selected.value = []
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}

// --- Ship (tracking or consolidation) ---
const shipDialog = ref(false)
const shipRef = ref('')
const shipTarget = ref<{ type: 'tracking' | 'consolidation'; id: string } | null>(null)

function openShipTracking(row: PendingTracking) {
  dialogError.value = null
  shipRef.value = row.tracking_ref ?? ''
  shipTarget.value = { type: 'tracking', id: row.tracking_id }
  shipDialog.value = true
}

function openShipConsolidation(c: Consolidation) {
  dialogError.value = null
  shipRef.value = c.tracking_ref ?? ''
  shipTarget.value = { type: 'consolidation', id: c.id }
  shipDialog.value = true
}

async function submitShip() {
  if (!shipTarget.value || !shipRef.value.trim()) return
  saving.value = true
  dialogError.value = null
  try {
    if (shipTarget.value.type === 'tracking') {
      await shipTracking(shipTarget.value.id, shipRef.value.trim())
    } else {
      await shipConsolidation(shipTarget.value.id, shipRef.value.trim())
    }
    shipDialog.value = false
    notice.value = 'Expédition enregistrée.'
    await load()
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Expédition impossible.'
  } finally {
    saving.value = false
  }
}

async function deliver(row: PendingTracking) {
  error.value = null
  try {
    await deliverTracking(row.tracking_id)
    notice.value = 'Colis marqué livré.'
    await load()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.'
  }
}

// --- Advance to next leg (tronçon suivant) ---
async function advanceTrackingRow(row: PendingTracking) {
  error.value = null
  try {
    const res = await advanceTracking(row.tracking_id)
    notice.value = res.message
    await load()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.'
  }
}

async function advanceConsolidationRow(c: Consolidation) {
  error.value = null
  try {
    const res = await advanceConsolidation(c.id)
    notice.value = res.message
    await load()
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.'
  }
}

// --- Journey (parcours du colis) ---
const journeyDialog = ref(false)
const journey = ref<JourneyLeg[]>([])
const journeyLoading = ref(false)
const journeyError = ref<string | null>(null)
const journeyOrderId = ref<string | null>(null)

const _legColors: Record<string, string> = {
  delivered: 'green',
  completed: 'teal',
  shipped: 'indigo',
  in_progress: 'blue',
  pending: 'grey',
}
function legColor(leg: JourneyLeg): string {
  return _legColors[leg.status_code ?? ''] ?? 'grey-7'
}
function legPath(leg: JourneyLeg): string {
  return `${leg.from_place ?? '?'} → ${leg.to_place ?? '?'}`
}

async function openJourney(row: PendingTracking) {
  journeyOrderId.value = row.order_id
  journey.value = []
  journeyError.value = null
  journeyLoading.value = true
  journeyDialog.value = true
  try {
    journey.value = await getOrderJourney(row.order_id)
  } catch (err) {
    journeyError.value = extractApiError(err) ?? 'Chargement du parcours impossible.'
  } finally {
    journeyLoading.value = false
  }
}

// --- Create consolidation from selection ---
const createDialog = ref(false)
const createName = ref('')

function openCreate() {
  dialogError.value = null
  createName.value = ''
  createDialog.value = true
}

async function submitCreate() {
  if (!createName.value.trim() || selected.value.length === 0) return
  // A consolidation groups trackings of a single route.
  const routeIds = new Set(selected.value.map((t) => t.route_id))
  if (routeIds.size > 1) {
    dialogError.value = 'Les colis sélectionnés doivent appartenir au même tronçon (route).'
    return
  }
  const first = selected.value[0]
  if (!first) return
  saving.value = true
  dialogError.value = null
  try {
    const consolidation = await createConsolidation({
      route_id: first.route_id,
      name: createName.value.trim(),
    })
    await addTrackings(
      consolidation.id,
      selected.value.map((t) => t.tracking_id),
    )
    createDialog.value = false
    notice.value = 'Consolidation créée.'
    await load()
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Création impossible.'
  } finally {
    saving.value = false
  }
}

void load()
</script>
