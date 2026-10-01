<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('shipping.title')" :hint="$t('shipping.hint')">
      <template #actions>
        <q-toggle v-model="showCompleted" :label="$t('shipping.show_done')" dense />
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <!-- Colis à grouper / traiter -->
    <section class="app-section" aria-labelledby="pending-title">
      <div class="app-section__head">
        <h2 id="pending-title" class="app-section__title">{{ $t('shipping.to_group') }}</h2>
        <p class="app-section__hint">
          {{ $t('shipping.to_group_hint') }}
        </p>
      </div>

      <div v-if="selected.length" class="admin-toolbar">
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:package"
          :label="$t('shipping.create_n', { n: selected.length })"
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
            <router-link
              :to="`/orders/${props.row.order_id}`"
              class="admin-link font-mono"
              :title="props.row.order_id"
              >#{{ props.row.order_id.slice(0, 8) }}</router-link
            >
          </q-td>
        </template>
        <template #body-cell-status="props">
          <q-td :props="props">
            <StatusTag
              :label="props.row.status_name || props.row.status_code || '—'"
              :tone="toneOf(statusColor(props.row.status_code))"
              :icon="toneIcon(toneOf(statusColor(props.row.status_code)))"
            />
          </q-td>
        </template>
        <template #body-cell-ref="props">
          <q-td :props="props" class="font-mono">{{ props.row.tracking_ref || '—' }}</q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn
              flat
              dense
              no-caps
              icon="ph:path"
              :label="$t('shipping.route')"
              @click="openJourney(props.row)"
            />
            <q-btn
              flat
              dense
              no-caps
              icon="ph:truck"
              :label="$t('shipping.hand_over')"
              :disable="isTerminal(props.row) || isShipped(props.row)"
              @click="openShipTracking(props.row)"
            >
              <q-tooltip max-width="320px">
                {{ $t('shipping.hand_over_tip') }}
              </q-tooltip>
            </q-btn>
            <q-btn
              flat
              dense
              no-caps
              icon="ph:skip-forward"
              :label="$t('shipping.next_leg')"
              :disable="isTerminal(props.row) || props.row.is_final_leg"
              @click="advanceTrackingRow(props.row)"
            >
              <q-tooltip v-if="props.row.is_final_leg" max-width="280px">
                {{ $t('shipping.last_leg') }}
              </q-tooltip>
            </q-btn>
            <q-btn
              flat
              dense
              no-caps
              icon="ph:check-circle"
              :label="$t('shipping.deliver')"
              :disable="isTerminal(props.row) || !props.row.is_final_leg"
              @click="deliver(props.row)"
            >
              <q-tooltip v-if="!props.row.is_final_leg" max-width="280px">
                {{ $t('shipping.last_only') }}
              </q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">{{ $t('shipping.none') }}</div>
        </template>
      </q-table>
    </section>

    <!-- Consolidations -->
    <section class="app-section" aria-labelledby="consolidations-title">
      <div class="app-section__head">
        <h2 id="consolidations-title" class="app-section__title">
          {{ $t('shipping.consolidations') }}
        </h2>
      </div>
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
        <template #body-cell-code="props">
          <q-td :props="props" class="font-mono">{{ props.row.consolidation_code }}</q-td>
        </template>
        <template #body-cell-status="props">
          <q-td :props="props">
            <StatusTag
              :label="props.row.status_name || props.row.status_code || '—'"
              :tone="toneOf(statusColor(props.row.status_code))"
              :icon="toneIcon(toneOf(statusColor(props.row.status_code)))"
            />
          </q-td>
        </template>
        <template #body-cell-total_orders="props">
          <q-td :props="props" class="font-mono">{{ props.row.total_orders }}</q-td>
        </template>
        <template #body-cell-ref="props">
          <q-td :props="props" class="font-mono">{{ props.row.tracking_ref || '—' }}</q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn
              flat
              dense
              no-caps
              icon="ph:truck"
              :label="$t('shipping.hand_over_all')"
              :disable="isTerminal(props.row) || isShipped(props.row)"
              @click="openShipConsolidation(props.row)"
            >
              <q-tooltip max-width="320px">
                {{ $t('shipping.hand_over_all_tip') }}
              </q-tooltip>
            </q-btn>
            <q-btn
              flat
              dense
              no-caps
              icon="ph:skip-forward"
              :label="$t('shipping.next_leg')"
              :disable="isTerminal(props.row)"
              @click="advanceConsolidationRow(props.row)"
            />
            <q-btn
              flat
              dense
              no-caps
              icon="ph:check-circle"
              :label="$t('shipping.deliver')"
              :disable="isTerminal(props.row)"
              @click="deliverConsolidationRow(props.row)"
            />
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('shipping.no_consolidation') }}
          </div>
        </template>
      </q-table>
    </section>

    <!-- Ship dialog (tracking ref) -->
    <q-dialog v-model="shipDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('shipping.hand_over_title') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitShip">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-select
              v-model="shipCarrierId"
              :options="carrierOptions"
              :label="$t('shipping.carrier')"
              outlined
              dense
              emit-value
              map-options
            />
            <q-input
              v-model="shipRef"
              :label="$t('shipping.tracking')"
              :hint="$t('shipping.tracking_hint')"
              outlined
              dense
              autofocus
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('shipping.hand_over')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Advance consolidation: keep or ungroup the lot -->
    <q-dialog v-model="ungroupDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('shipping.next_title') }}</h2>
          <p class="app-dialog__text">
            {{ $t('shipping.keep_q') }}
          </p>
        </q-card-section>
        <q-card-section>
          <q-option-group
            v-model="ungroupChoice"
            :options="[
              { label: $t('shipping.keep'), value: 'keep' },
              { label: $t('shipping.ungroup'), value: 'ungroup' },
            ]"
            color="primary"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :label="$t('shipping.validate')"
            :loading="ungroupBusy"
            @click="submitAdvanceConsolidation"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Journey dialog (parcours du colis) -->
    <q-dialog v-model="journeyDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('shipping.route_title') }}</h2>
          <p class="app-dialog__text">
            {{ $t('shipping.order') }}
            <span class="font-mono">#{{ journeyOrderId?.slice(0, 8) }}</span>
          </p>
        </q-card-section>
        <q-card-section>
          <AppNotice v-if="journeyError" tone="error" dense>{{ journeyError }}</AppNotice>
          <div v-else-if="journeyLoading" class="text-center q-pa-md">
            <q-spinner size="2em" />
          </div>
          <div v-else-if="journey.length === 0" class="text-subtle q-pa-md text-center">
            {{ $t('shipping.no_leg') }}
          </div>
          <q-timeline v-else layout="comfortable">
            <q-timeline-entry
              v-for="leg in journey"
              :key="leg.tracking_id"
              :title="$t('shipping.leg_title', { n: leg.sequence_order, path: legPath(leg) })"
              :subtitle="leg.route_name || ''"
              :icon="leg.is_current ? 'ph:crosshair' : 'ph:map-pin'"
            >
              <div class="row items-center q-gutter-sm">
                <StatusTag
                  :label="leg.status_name || leg.status_code || '—'"
                  :tone="toneOf(legColor(leg))"
                  :icon="toneIcon(toneOf(legColor(leg)))"
                />
                <span v-if="leg.mode" class="text-caption text-muted">{{ leg.mode }}</span>
                <span v-if="leg.tracking_ref" class="text-caption"
                  >{{ $t('shipping.ref') }}
                  <span class="font-mono">{{ leg.tracking_ref }}</span></span
                >
                <StatusTag
                  v-if="leg.is_current"
                  tone="warn"
                  icon="ph:crosshair"
                  :label="$t('shipping.current')"
                />
              </div>
            </q-timeline-entry>
          </q-timeline>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.close')" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Create consolidation dialog -->
    <q-dialog v-model="createDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('shipping.new_consolidation') }}</h2>
          <p class="app-dialog__text">{{ $t('shipping.n_selected', { n: selected.length }) }}</p>
        </q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="createName"
              :label="$t('shipping.consolidation_name')"
              outlined
              dense
              autofocus
              :rules="[(v) => (!!v && v.trim().length > 0) || $t('shipping.name_rule')]"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('shipping.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, ref } from 'vue';
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, toneOf } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
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

const { t } = useI18n();

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

const pendingColumns = computed<QTableColumn[]>(() => [
  { name: 'order', label: t('shipping.col_order'), field: 'order_id', align: 'left' },
  {
    name: 'sequence',
    label: t('shipping.col_leg'),
    field: 'sequence_order',
    align: 'left',
    format: (v: number) => t('shipping.leg_n', { n: v }),
  },
  { name: 'status', label: t('shipping.col_status'), field: 'status_code', align: 'left' },
  { name: 'ref', label: t('shipping.col_ref'), field: 'tracking_ref', align: 'left' },
  { name: 'actions', label: '', field: 'tracking_id', align: 'right' },
]);

const consolidationColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('shipping.col_name'), field: 'name', align: 'left' },
  { name: 'code', label: t('shipping.col_code'), field: 'consolidation_code', align: 'left' },
  { name: 'status', label: t('shipping.col_status'), field: 'status_code', align: 'left' },
  { name: 'total_orders', label: t('shipping.col_parcels'), field: 'total_orders', align: 'left' },
  { name: 'ref', label: t('shipping.col_ref'), field: 'tracking_ref', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

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
    error.value = extractApiError(err) ?? t('common.load_failed');
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
  showCompleted.value ? consolidations.value : consolidations.value.filter((c) => !isTerminal(c)),
);

// --- Ship (tracking or consolidation) ---
const shipDialog = ref(false);
const shipRef = ref('');
const shipCarrierId = ref<string | null>(null);
const shipTarget = ref<{ type: 'tracking' | 'consolidation'; id: string } | null>(null);

const carrierOptions = computed<{ label: string; value: string | null }[]>(() => [
  { label: t('shipping.internal'), value: null },
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
    notice.value = t('shipping.handed_over');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('shipping.ship_failed');
  } finally {
    saving.value = false;
  }
}

async function deliver(row: PendingTracking) {
  error.value = null;
  try {
    await deliverTracking(row.tracking_id);
    notice.value = t('shipping.delivered');
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.op_failed');
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
    error.value = extractApiError(err) ?? t('common.op_failed');
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
    error.value = extractApiError(err) ?? t('common.op_failed');
  } finally {
    ungroupBusy.value = false;
  }
}

function deliverConsolidationRow(c: Consolidation) {
  $q.dialog({
    title: t('shipping.deliver_batch'),
    message: t('shipping.deliver_batch_msg'),
    cancel: true,
    ok: { label: t('shipping.deliver'), color: 'positive' },
  }).onOk(() => {
    void (async () => {
      error.value = null;
      try {
        const res = await deliverConsolidation(c.id);
        notice.value = res.message;
        await load();
      } catch (err) {
        error.value = extractApiError(err) ?? t('common.op_failed');
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
function statusColor(code: string | null): string {
  return _legColors[code ?? ''] ?? 'grey-7';
}
function legColor(leg: JourneyLeg): string {
  return statusColor(leg.status_code);
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
    journeyError.value = extractApiError(err) ?? t('shipping.route_failed');
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
    dialogError.value = t('shipping.same_leg');
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
    notice.value = t('shipping.created');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.create_failed');
  } finally {
    saving.value = false;
  }
}

void load();
</script>
