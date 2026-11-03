<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('delivery_modes.title')" :hint="$t('delivery_modes.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('logistics.new_delivery_mode')"
          :disable="!mainWarehouse"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
      <AppNotice v-if="loaded && !mainWarehouse" tone="warning" data-testid="no-main-warehouse">
        {{ $t('delivery_modes.no_warehouse') }}
        <template #action>
          <q-btn
            flat
            no-caps
            icon="ph:warehouse"
            :label="$t('delivery_modes.create_warehouse')"
            :loading="creatingWarehouse"
            @click="createMainWarehouse"
          />
        </template>
      </AppNotice>
      <AppNotice v-else-if="loaded && activeCount === 0" tone="info" dense>
        {{ $t('delivery_modes.none_active') }}
      </AppNotice>
    </div>

    <section class="app-section">
      <q-table
        :rows="modes"
        :columns="columns"
        row-key="id"
        flat
        bordered
        :rows-per-page-options="[0]"
        hide-pagination
        :loading="loading"
      >
        <template #body-cell-mode="props">
          <q-td :props="props">
            <div class="text-weight-medium">
              {{
                props.row.customer_label || deliveryTypeLabel(props.row.last_leg_delivery_type, t)
              }}
            </div>
            <div v-if="props.row.customer_label" class="text-caption text-muted">
              {{ deliveryTypeLabel(props.row.last_leg_delivery_type, t) }}
            </div>
          </q-td>
        </template>
        <template #body-cell-price="props">
          <q-td :props="props" class="font-mono">{{ priceSummary(props.row) }}</q-td>
        </template>
        <template #body-cell-free="props">
          <q-td :props="props" class="font-mono">
            {{ props.row.free_shipping_threshold ? `≥ ${props.row.free_shipping_threshold}` : '—' }}
          </q-td>
        </template>
        <template #body-cell-eta="props">
          <q-td :props="props">
            {{
              props.row.eta_days != null
                ? $t('delivery_modes.days', { n: props.row.eta_days })
                : '—'
            }}
          </q-td>
        </template>
        <template #body-cell-where="props">
          <q-td :props="props">{{ whereSummary(props.row) }}</q-td>
        </template>
        <template #body-cell-active="props">
          <q-td :props="props">
            <q-toggle
              :model-value="props.row.is_active"
              dense
              :aria-label="$t('delivery_modes.col_active')"
              @update:model-value="(v: boolean) => toggleActive(props.row, v)"
            />
          </q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
              <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('delivery_modes.empty') }}
          </div>
        </template>
      </q-table>
    </section>

    <DeliveryModeDialog
      v-model="dialog"
      :route="editing"
      :places="places"
      :routes="routes"
      @saved="onSaved"
      @place-created="load"
    />
  </q-page>
</template>

<script setup lang="ts">
/**
 * Modes de livraison proposés au client, toujours accessible (y compris en
 * mode simple, sans le module « Trajets et lieux ») : c'est ici qu'une
 * boutique basique fixe ses frais de port — forfait, franco, retrait.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import PageHeader from '@/components/PageHeader.vue';
import DeliveryModeDialog from '@/components/DeliveryModeDialog.vue';
import {
  createPlace,
  getRouteServedPlaces,
  listPlaces,
  listRoutes,
  setMainWarehouse,
  updateRoute,
  type Place,
  type ShippingRoute,
} from '@/api/logistics';
import { extractApiError } from '@/api/errors';
import { deliveryTypeLabel } from '@/utils/deliveryModes';

const { t } = useI18n();

const places = ref<Place[]>([]);
const routes = ref<ShippingRoute[]>([]);
const servedCount = ref<Record<string, number>>({});
const loading = ref(false);
const loaded = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const modes = computed(() =>
  routes.value.filter((r) => r.is_to_customer && !!r.last_leg_delivery_type),
);
const activeCount = computed(() => modes.value.filter((r) => r.is_active).length);
const placeById = computed(() => new Map(places.value.map((p) => [p.id, p])));
const mainWarehouse = computed(() => places.value.find((p) => p.is_main_warehouse) ?? null);

const columns = computed<QTableColumn[]>(() => [
  { name: 'mode', label: t('delivery_modes.col_mode'), field: 'customer_label', align: 'left' },
  { name: 'price', label: t('delivery_modes.col_price'), field: 'base_price', align: 'left' },
  {
    name: 'free',
    label: t('delivery_modes.col_free'),
    field: 'free_shipping_threshold',
    align: 'left',
  },
  { name: 'eta', label: t('delivery_modes.col_eta'), field: 'eta_days', align: 'left' },
  { name: 'where', label: t('delivery_modes.col_where'), field: 'to_place_id', align: 'left' },
  { name: 'active', label: t('delivery_modes.col_active'), field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

function priceSummary(r: ShippingRoute): string {
  const parts: string[] = [];
  if (Number(r.base_price ?? 0) > 0) parts.push(r.base_price ?? '');
  if (Number(r.price_per_kg ?? 0) > 0) parts.push(`${r.price_per_kg}/kg`);
  if (r.weight_bands?.length) {
    parts.push(t('delivery_modes.bands', { n: r.weight_bands.length }, r.weight_bands.length));
  }
  return parts.length > 0 ? parts.join(' + ') : t('delivery_modes.free');
}

function whereSummary(r: ShippingRoute): string {
  if (r.mode === 'pickup') {
    const place = placeById.value.get(r.to_place_id);
    return place ? t('delivery_modes.pickup_at', { place: place.name }) : '—';
  }
  const n = servedCount.value[r.id] ?? 0;
  return n > 0 && !r.always_available
    ? t('delivery_modes.zones', { n }, n)
    : t('delivery_modes.everywhere');
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [places.value, routes.value] = await Promise.all([listPlaces(), listRoutes(true)]);
    const scoped = modes.value.filter((r) => !r.always_available && r.mode !== 'pickup');
    const counts = await Promise.all(
      scoped.map((r) =>
        getRouteServedPlaces(r.id).then((served) => [r.id, served.length] as const),
      ),
    );
    servedCount.value = Object.fromEntries(counts);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
    loaded.value = true;
  }
}

// --- Entrepôt principal manquant (boutique migrée sans entrepôt) ---
const creatingWarehouse = ref(false);
async function createMainWarehouse() {
  creatingWarehouse.value = true;
  error.value = null;
  try {
    const country = places.value.find((p) => p.type === 'country' && !p.parent_id) ?? null;
    const warehouse = await createPlace({
      name: t('delivery_modes.warehouse_name'),
      type: 'warehouse',
      is_warehouse: true,
      country: country?.country ?? null,
      parent_id: country?.id ?? null,
    });
    await setMainWarehouse(warehouse.id);
    notice.value = t('logistics.main_set', { name: warehouse.name });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    creatingWarehouse.value = false;
  }
}

async function toggleActive(r: ShippingRoute, value: boolean) {
  error.value = null;
  try {
    const saved = await updateRoute(r.id, { is_active: value });
    routes.value = routes.value.map((x) => (x.id === saved.id ? saved : x));
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  }
}

// --- Dialogue ---
const dialog = ref(false);
const editing = ref<ShippingRoute | null>(null);
function openCreate() {
  editing.value = null;
  notice.value = null;
  dialog.value = true;
}
function openEdit(r: ShippingRoute) {
  editing.value = r;
  notice.value = null;
  dialog.value = true;
}
async function onSaved() {
  notice.value = t('delivery_modes.saved');
  await load();
}

onMounted(load);
</script>
