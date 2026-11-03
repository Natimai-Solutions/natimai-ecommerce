<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('logistics.title')" :hint="$t('logistics.hint')">
      <template #actions>
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

    <!-- Lieux -->
    <section class="app-section" aria-labelledby="places-title">
      <div class="app-section__head">
        <h2 id="places-title" class="app-section__title">{{ $t('logistics.places') }}</h2>
        <p class="app-section__hint">
          {{ $t('logistics.places_hint') }}
        </p>
        <q-btn
          class="app-section__action"
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('logistics.new_place')"
          @click="openPlaceCreate"
        />
      </div>
      <q-table
        :rows="places"
        :columns="placeColumns"
        row-key="id"
        flat
        bordered
        :rows-per-page-options="[0]"
        hide-pagination
        :loading="loading"
      >
        <template #body-cell-parent="props">
          <q-td :props="props">
            <span v-if="props.row.parent_id">{{ placeName(props.row.parent_id) }}</span>
            <span v-else>—</span>
          </q-td>
        </template>
        <template #body-cell-code="props">
          <q-td :props="props" class="font-mono">{{ props.row.code ?? '' }}</q-td>
        </template>
        <template #body-cell-warehouse="props">
          <q-td :props="props">
            <StatusTag
              v-if="props.row.is_main_warehouse"
              :label="$t('logistics.main')"
              tone="ok"
              icon="ph:star"
            />
            <q-icon v-else-if="props.row.is_warehouse" name="ph:check" class="text-positive" />
            <span v-else>—</span>
          </q-td>
        </template>
        <template #body-cell-customs="props">
          <q-td :props="props">
            <q-icon v-if="props.row.customs_clearance" name="ph:check" class="text-positive" />
            <span v-else>—</span>
          </q-td>
        </template>
        <template #body-cell-origin="props">
          <q-td :props="props">{{ originSummary(props.row) }}</q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn
              v-if="props.row.is_warehouse && !props.row.is_main_warehouse"
              flat
              round
              dense
              icon="ph:star"
              @click="makeMainWarehouse(props.row)"
            >
              <q-tooltip max-width="300px">
                {{ $t('logistics.main_tip') }}
              </q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:pencil-simple" @click="openPlaceEdit(props.row)">
              <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('logistics.no_place') }}
          </div>
        </template>
      </q-table>
    </section>

    <!-- Trajets -->
    <section class="app-section" aria-labelledby="routes-title">
      <div class="app-section__head">
        <h2 id="routes-title" class="app-section__title">{{ $t('logistics.routes') }}</h2>
        <p class="app-section__hint">
          {{ $t('logistics.routes_hint') }}
        </p>
        <q-btn
          class="app-section__action"
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('logistics.new_route')"
          :disable="places.length < 2"
          @click="openRouteCreate"
        />
        <q-btn
          class="app-section__action"
          flat
          no-caps
          icon="ph:package"
          :label="$t('logistics.new_delivery_mode')"
          @click="openDeliveryCreate"
        />
      </div>
      <q-table
        :rows="routes"
        :columns="routeColumns"
        row-key="id"
        flat
        bordered
        :rows-per-page-options="[0]"
        hide-pagination
        :loading="loading"
      >
        <template #body-cell-path="props">
          <q-td :props="props">
            {{ placeName(props.row.from_place_id) }}
            <q-icon name="ph:arrow-right" size="14px" class="text-subtle" />
            {{ placeName(props.row.to_place_id) }}
          </q-td>
        </template>
        <template #body-cell-mode="props">
          <q-td :props="props">{{ modeLabel(props.row.mode) }}</q-td>
        </template>
        <template #body-cell-delivery_mode="props">
          <q-td :props="props">
            {{
              props.row.last_leg_delivery_type
                ? deliveryTypeLabel(props.row.last_leg_delivery_type, t)
                : '—'
            }}
          </q-td>
        </template>
        <template #body-cell-tariff="props">
          <q-td :props="props" class="font-mono">{{ tariffSummary(props.row) }}</q-td>
        </template>
        <template #body-cell-to_customer="props">
          <q-td :props="props">
            <q-icon v-if="props.row.is_to_customer" name="ph:check" class="text-positive" />
            <span v-else>—</span>
          </q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn flat round dense icon="ph:pencil-simple" @click="openRouteEdit(props.row)">
              <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('logistics.no_route') }}
          </div>
        </template>
      </q-table>
    </section>

    <!-- Place dialog -->
    <q-dialog v-model="placeDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ placeEditId ? $t('logistics.edit_place') : $t('logistics.new_place_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitPlace">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="placeForm.name"
              :label="$t('logistics.name')"
              outlined
              dense
              bottom-slots
              :rules="req"
            />
            <q-select
              v-model="placeForm.type"
              :options="placeTypeOptions"
              :label="$t('logistics.type')"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              :rules="req"
            />
            <q-select
              v-model="placeForm.parent_id"
              :options="parentOptions"
              :label="$t('logistics.parent')"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              clearable
              :hint="$t('logistics.parent_hint')"
            />
            <q-input
              v-model="placeForm.code"
              :label="$t('logistics.code')"
              outlined
              dense
              bottom-slots
            />
            <div class="row" style="gap: 8px">
              <q-input
                v-model="placeForm.city"
                :label="$t('logistics.city')"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-select
                v-model="placeForm.country"
                :options="filteredCountryOptions"
                :label="$t('logistics.country')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                use-input
                input-debounce="0"
                clearable
                class="col"
                @filter="filterCountries"
              />
            </div>
            <template v-if="!isGeoType(placeForm.type)">
              <q-input
                v-model="placeForm.address_line1"
                :label="$t('logistics.address1')"
                outlined
                dense
                bottom-slots
                :hint="$t('logistics.address_hint')"
              />
              <div class="row" style="gap: 8px">
                <q-input
                  v-model="placeForm.address_line2"
                  :label="$t('logistics.address2')"
                  outlined
                  dense
                  bottom-slots
                  class="col"
                />
                <q-input
                  v-model="placeForm.postal_code"
                  :label="$t('logistics.postcode')"
                  outlined
                  dense
                  bottom-slots
                  class="col-4"
                />
              </div>
            </template>
            <q-select
              v-if="isGeoType(placeForm.type)"
              v-model="placePostalCodes"
              :label="$t('logistics.postcodes')"
              outlined
              dense
              bottom-slots
              multiple
              use-chips
              use-input
              input-debounce="0"
              new-value-mode="add-unique"
              hide-dropdown-icon
              :options="[]"
              :hint="$t('logistics.postcodes_hint')"
            />
            <q-toggle v-model="placeForm.is_warehouse" :label="$t('logistics.warehouse')" />
            <q-toggle v-model="placeForm.customs_clearance" :label="$t('logistics.clearance')" />
            <template v-if="!isGeoType(placeForm.type)">
              <q-select
                v-model="placeForm.customs_regime"
                :options="customsRegimeOptions"
                :label="$t('logistics.regime')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                :hint="$t('logistics.regime_hint')"
              />
              <q-toggle v-model="placeForm.dropship_enabled" :label="$t('logistics.dropship')" />
            </template>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="placeEditId ? $t('common.save') : $t('common.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Route dialog : tronçons logistiques. Les modes de livraison client
         (tronçon final typé) passent par DeliveryModeDialog. -->
    <q-dialog v-model="routeDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ routeEditId ? $t('logistics.edit_route') : $t('logistics.new_route_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitRoute">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="routeForm.name"
              :label="$t('logistics.route_name')"
              outlined
              dense
              bottom-slots
              :rules="req"
            />
            <div class="row" style="gap: 8px">
              <q-select
                v-model="routeForm.from_place_id"
                :options="placeOptions"
                :label="$t('logistics.from')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                class="col"
                :rules="req"
              />
              <q-select
                v-model="routeForm.to_place_id"
                :options="placeOptions"
                :label="$t('logistics.to')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                class="col"
                :rules="req"
              />
            </div>
            <div class="row" style="gap: 8px">
              <q-select
                v-model="routeForm.mode"
                :options="modeOptions"
                :label="$t('logistics.mode')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                class="col"
                :rules="req"
              />
              <q-select
                v-model="routeForm.service_level"
                :options="serviceLevelOptions"
                :label="$t('logistics.service')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                clearable
                class="col"
              />
            </div>
            <q-input
              v-model="routeForm.customer_label"
              :label="$t('logistics.customer_label')"
              outlined
              dense
              bottom-slots
            />
            <div class="row" style="gap: 8px">
              <q-input
                v-model.number="routeForm.eta_days"
                :label="$t('logistics.eta')"
                type="number"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-input
                v-model="routeForm.price_per_kg"
                :label="$t('logistics.per_kg', { currency: shopConfig.currency })"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-input
                v-model="routeForm.base_price"
                :label="$t('logistics.flat', { currency: shopConfig.currency })"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
            </div>
            <WeightBandsEditor v-model="routeBands" :currency="shopConfig.currency" />
            <q-input
              v-model="routeForm.free_shipping_threshold"
              :label="$t('logistics.free_from', { currency: shopConfig.currency })"
              type="number"
              step="0.01"
              outlined
              dense
              bottom-slots
              clearable
              :hint="$t('logistics.free_hint')"
            />
            <!-- Tronçon final non proposé au checkout (ex. fournisseur en
                 dropshipping → client) : il n'a pas de mode de livraison. -->
            <q-toggle v-model="routeForm.is_to_customer" :label="$t('logistics.final_untyped')" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="routeEditId ? $t('common.save') : $t('common.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <DeliveryModeDialog
      v-model="deliveryDialog"
      :route="deliveryEditing"
      :places="places"
      :routes="routes"
      @saved="onDeliverySaved"
      @place-created="load"
    />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useShopConfigStore } from '@/stores/shopConfig';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { countryOptions, type CountryOption } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import DeliveryModeDialog from '@/components/DeliveryModeDialog.vue';
import WeightBandsEditor from '@/components/WeightBandsEditor.vue';
import {
  createPlace,
  createRoute,
  getPlacePostalCodes,
  listPlaces,
  listRoutes,
  setPlacePostalCodes,
  updatePlace,
  updateRoute,
  type Place,
  type ShippingRoute,
  setMainWarehouse,
} from '@/api/logistics';
import { deliveryTypeLabel } from '@/utils/deliveryModes';
import { bandRows, bandsPayload, type BandRow } from '@/utils/weightBands';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();
const shopConfig = useShopConfigStore();

const places = ref<Place[]>([]);
const routes = ref<ShippingRoute[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];

// Sélecteur pays ISO (PF/FR épinglés), filtrable à la saisie.
const allCountryOptions = countryOptions();
const filteredCountryOptions = ref<CountryOption[]>(allCountryOptions);
function filterCountries(val: string, update: (fn: () => void) => void) {
  update(() => {
    const needle = val.trim().toLowerCase();
    filteredCountryOptions.value = needle
      ? allCountryOptions.filter((o) => o.label.toLowerCase().includes(needle))
      : allCountryOptions;
  });
}

const placeTypeOptions = computed(() => [
  { label: t('logistics.pt_warehouse'), value: 'warehouse' },
  { label: t('logistics.pt_airport'), value: 'airport' },
  { label: t('logistics.pt_port'), value: 'seaport' },
  { label: t('logistics.pt_shop'), value: 'shop' },
  { label: t('logistics.pt_country'), value: 'country' },
  { label: t('logistics.pt_region'), value: 'region' },
  { label: t('logistics.pt_island'), value: 'island' },
  { label: t('logistics.pt_municipality'), value: 'municipality' },
  { label: t('logistics.pt_address'), value: 'address' },
]);
// Zones géographiques : forment l'arbre de desserte + portent les codes postaux.
const GEO_TYPES = ['country', 'region', 'island', 'municipality'];
function isGeoType(type: string): boolean {
  return GEO_TYPES.includes(type);
}
const modeOptions = computed(() => [
  { label: t('logistics.m_air'), value: 'air' },
  { label: t('logistics.m_sea'), value: 'sea' },
  { label: t('logistics.m_road'), value: 'road' },
  { label: t('logistics.m_pickup'), value: 'pickup' },
]);
const serviceLevelOptions = computed(() => [
  { label: t('logistics.s_fast'), value: 'rapide' },
  { label: t('logistics.s_eco'), value: 'economique' },
  { label: t('logistics.s_green'), value: 'ecologique' },
]);
function modeLabel(mode: string): string {
  return modeOptions.value.find((o) => o.value === mode)?.label ?? mode;
}
const placeById = computed(() => new Map(places.value.map((p) => [p.id, p])));
const placeOptions = computed(() =>
  places.value.map((p) => ({ label: `${p.name}${p.code ? ` (${p.code})` : ''}`, value: p.id })),
);
// Zones candidates comme parent ou comme desserte (pas les nœuds opérationnels),
// libellées avec leur chaîne parente pour lever les ambiguïtés.
const geoPlaceOptions = computed(() =>
  places.value
    .filter((p) => isGeoType(p.type))
    .map((p) => ({ label: placePathLabel(p), value: p.id }))
    .sort((a, b) => a.label.localeCompare(b.label)),
);
// Le parent d'un lieu peut être n'importe quelle zone géo (une boutique a pour
// parent sa commune/île) — on exclut le lieu lui-même à l'édition.
const parentOptions = computed(() =>
  geoPlaceOptions.value.filter((o) => o.value !== placeEditId.value),
);
function placeName(id: string): string {
  return placeById.value.get(id)?.name ?? id.slice(0, 8);
}
function placePathLabel(place: Place): string {
  const parts = [place.name];
  let current = place;
  for (let depth = 0; depth < 6; depth += 1) {
    const parent = current.parent_id ? placeById.value.get(current.parent_id) : undefined;
    if (!parent) break;
    parts.push(parent.name);
    current = parent;
  }
  return parts.join(' ‹ ');
}

const placeColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('logistics.col_name'), field: 'name', align: 'left' },
  { name: 'type', label: t('logistics.col_type'), field: 'type', align: 'left' },
  { name: 'parent', label: t('logistics.col_parent'), field: 'parent_id', align: 'left' },
  { name: 'code', label: t('logistics.col_code'), field: 'code', align: 'left' },
  { name: 'city', label: t('logistics.col_city'), field: 'city', align: 'left' },
  { name: 'country', label: t('logistics.col_country'), field: 'country', align: 'left' },
  {
    name: 'warehouse',
    label: t('logistics.col_warehouse'),
    field: 'is_warehouse',
    align: 'center',
  },
  {
    name: 'customs',
    label: t('logistics.col_customs'),
    field: 'customs_clearance',
    align: 'center',
  },
  { name: 'origin', label: t('logistics.col_origin'), field: 'customs_regime', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

const customsRegimeOptions = computed(() => [
  { label: t('logistics.r_auto'), value: null },
  { label: t('logistics.r_local'), value: 'domestic' },
  { label: t('logistics.r_import'), value: 'import' },
]);

function originSummary(p: Place): string {
  const parts: string[] = [];
  if (p.customs_regime === 'domestic') parts.push('local');
  else if (p.customs_regime === 'import') parts.push('import');
  if (p.dropship_enabled) parts.push('dropship');
  return parts.length > 0 ? parts.join(' · ') : '—';
}

async function makeMainWarehouse(p: Place) {
  error.value = null;
  try {
    await setMainWarehouse(p.id);
    notice.value = t('logistics.main_set', { name: p.name });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.op_failed');
  }
}
const routeColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('logistics.col_name'), field: 'name', align: 'left' },
  { name: 'path', label: t('logistics.col_path'), field: 'from_place_id', align: 'left' },
  { name: 'mode', label: t('logistics.col_mode'), field: 'mode', align: 'left' },
  {
    name: 'service_level',
    label: t('logistics.col_service'),
    field: 'service_level',
    align: 'left',
  },
  { name: 'eta', label: t('logistics.col_eta'), field: 'eta_days', align: 'left' },
  { name: 'price_per_kg', label: t('logistics.col_per_kg'), field: 'price_per_kg', align: 'left' },
  { name: 'base_price', label: t('logistics.col_flat'), field: 'base_price', align: 'left' },
  { name: 'tariff', label: t('logistics.col_tariff'), field: 'weight_bands', align: 'left' },
  {
    name: 'delivery_mode',
    label: t('logistics.col_last_leg'),
    field: 'last_leg_delivery_type',
    align: 'left',
  },
  {
    name: 'to_customer',
    label: t('logistics.col_final'),
    field: 'is_to_customer',
    align: 'center',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [places.value, routes.value] = await Promise.all([listPlaces(), listRoutes()]);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// --- Place create / edit ---
const placeDialog = ref(false);
const placeEditId = ref<string | null>(null);
const placeForm = reactive({
  name: '',
  type: 'warehouse',
  code: '',
  city: '',
  country: null as string | null,
  address_line1: '',
  address_line2: '',
  postal_code: '',
  parent_id: null as string | null,
  is_warehouse: true,
  customs_clearance: false,
  customs_regime: null as string | null,
  dropship_enabled: false,
});
const placePostalCodes = ref<string[]>([]);

function resetPlaceForm() {
  placeForm.name = '';
  placeForm.type = 'warehouse';
  placeForm.code = '';
  placeForm.city = '';
  placeForm.country = null;
  placeForm.address_line1 = '';
  placeForm.address_line2 = '';
  placeForm.postal_code = '';
  placeForm.parent_id = null;
  placeForm.is_warehouse = true;
  placeForm.customs_clearance = false;
  placeForm.customs_regime = null;
  placeForm.dropship_enabled = false;
  placePostalCodes.value = [];
}

function openPlaceCreate() {
  dialogError.value = null;
  placeEditId.value = null;
  resetPlaceForm();
  placeDialog.value = true;
}

function openPlaceEdit(p: Place) {
  dialogError.value = null;
  placeEditId.value = p.id;
  placeForm.name = p.name;
  placeForm.type = p.type;
  placeForm.code = p.code ?? '';
  placeForm.city = p.city ?? '';
  placeForm.country = p.country;
  placeForm.address_line1 = p.address_line1 ?? '';
  placeForm.address_line2 = p.address_line2 ?? '';
  placeForm.postal_code = p.postal_code ?? '';
  placeForm.parent_id = p.parent_id;
  placeForm.is_warehouse = p.is_warehouse;
  placeForm.customs_clearance = p.customs_clearance;
  placeForm.customs_regime = p.customs_regime;
  placeForm.dropship_enabled = p.dropship_enabled;
  placePostalCodes.value = [];
  if (isGeoType(p.type)) {
    getPlacePostalCodes(p.id)
      .then((codes) => {
        placePostalCodes.value = codes;
      })
      .catch(() => {
        // Non bloquant : l'édition des autres champs reste possible.
      });
  }
  placeDialog.value = true;
}

async function submitPlace() {
  const country = (placeForm.country ?? '').trim().toUpperCase();
  const codes = placePostalCodes.value.map((c) => c.trim()).filter((c) => c.length > 0);
  if (isGeoType(placeForm.type) && codes.length > 0 && !country) {
    dialogError.value = t('logistics.country_required');
    return;
  }
  saving.value = true;
  dialogError.value = null;
  const payload = {
    name: placeForm.name.trim(),
    type: placeForm.type,
    code: placeForm.code.trim() || null,
    city: placeForm.city.trim() || null,
    country: country || null,
    // Une zone géographique n'a pas d'adresse postale (ses codes postaux
    // servent à la déduction de zone, pas à l'affichage).
    address_line1: isGeoType(placeForm.type) ? null : placeForm.address_line1.trim() || null,
    address_line2: isGeoType(placeForm.type) ? null : placeForm.address_line2.trim() || null,
    postal_code: isGeoType(placeForm.type) ? null : placeForm.postal_code.trim() || null,
    parent_id: placeForm.parent_id,
    is_warehouse: placeForm.is_warehouse,
    customs_clearance: placeForm.customs_clearance,
    customs_regime: isGeoType(placeForm.type) ? null : placeForm.customs_regime,
    dropship_enabled: isGeoType(placeForm.type) ? false : placeForm.dropship_enabled,
  };
  try {
    let saved: Place;
    if (placeEditId.value) {
      saved = await updatePlace(placeEditId.value, payload);
    } else {
      saved = await createPlace(payload);
    }
    if (isGeoType(placeForm.type) && country) {
      await setPlacePostalCodes(saved.id, country, codes);
    }
    placeDialog.value = false;
    notice.value = t('logistics.place_saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

// --- Route create / edit (tronçons logistiques) ---
const routeDialog = ref(false);
const routeEditId = ref<string | null>(null);
const routeForm = reactive<{
  name: string;
  from_place_id: string | null;
  to_place_id: string | null;
  mode: string;
  service_level: string | null;
  customer_label: string;
  eta_days: number | null;
  price_per_kg: string;
  base_price: string;
  free_shipping_threshold: string;
  is_to_customer: boolean;
}>({
  name: '',
  from_place_id: null,
  to_place_id: null,
  mode: 'sea',
  service_level: null,
  customer_label: '',
  eta_days: null,
  price_per_kg: '',
  base_price: '',
  free_shipping_threshold: '',
  is_to_customer: false,
});
const routeBands = ref<BandRow[]>([]);

function tariffSummary(r: ShippingRoute): string {
  const parts: string[] = [];
  if (r.weight_bands && r.weight_bands.length > 0) {
    parts.push(`${r.weight_bands.length} tranche${r.weight_bands.length > 1 ? 's' : ''}`);
  }
  if (r.free_shipping_threshold) {
    parts.push(t('logistics.free_ge', { amount: r.free_shipping_threshold }));
  }
  return parts.length > 0 ? parts.join(' · ') : '—';
}

function resetRouteForm() {
  routeForm.name = '';
  routeForm.from_place_id = null;
  routeForm.to_place_id = null;
  routeForm.mode = 'sea';
  routeForm.service_level = null;
  routeForm.customer_label = '';
  routeForm.eta_days = null;
  routeForm.price_per_kg = '';
  routeForm.base_price = '';
  routeForm.free_shipping_threshold = '';
  routeForm.is_to_customer = false;
  routeBands.value = [];
}

function openRouteCreate() {
  dialogError.value = null;
  routeEditId.value = null;
  resetRouteForm();
  routeDialog.value = true;
}

function openRouteEdit(r: ShippingRoute) {
  // Un mode de livraison client a son propre formulaire, simplifié.
  if (r.is_to_customer && r.last_leg_delivery_type) {
    openDeliveryEdit(r);
    return;
  }
  dialogError.value = null;
  routeEditId.value = r.id;
  routeForm.name = r.name;
  routeForm.from_place_id = r.from_place_id;
  routeForm.to_place_id = r.to_place_id;
  routeForm.mode = r.mode;
  routeForm.service_level = r.service_level;
  routeForm.customer_label = r.customer_label ?? '';
  routeForm.eta_days = r.eta_days;
  routeForm.price_per_kg = r.price_per_kg ?? '';
  routeForm.base_price = r.base_price ?? '';
  routeForm.free_shipping_threshold = r.free_shipping_threshold ?? '';
  routeForm.is_to_customer = r.is_to_customer;
  routeBands.value = bandRows(r.weight_bands);
  routeDialog.value = true;
}

async function submitRoute() {
  if (!routeForm.from_place_id || !routeForm.to_place_id) {
    dialogError.value = t('logistics.ends_required');
    return;
  }
  if (routeForm.from_place_id === routeForm.to_place_id) {
    dialogError.value = t('logistics.ends_differ');
    return;
  }
  saving.value = true;
  dialogError.value = null;
  const payload = {
    name: routeForm.name.trim(),
    from_place_id: routeForm.from_place_id,
    to_place_id: routeForm.to_place_id,
    mode: routeForm.mode,
    service_level: routeForm.service_level || null,
    customer_label: routeForm.customer_label.trim() || null,
    // v-model.number leaves an empty field as "" at runtime — coerce to null.
    eta_days:
      typeof routeForm.eta_days === 'number' && !Number.isNaN(routeForm.eta_days)
        ? routeForm.eta_days
        : null,
    price_per_kg: routeForm.price_per_kg.trim() || null,
    base_price: routeForm.base_price.trim() || null,
    weight_bands: bandsPayload(routeBands.value),
    // q-input clearable sets null; keep the payload a string or null.
    free_shipping_threshold: (routeForm.free_shipping_threshold ?? '').trim() || null,
    is_to_customer: routeForm.is_to_customer,
    last_leg_delivery_type: null,
    always_available: false,
  };
  try {
    if (routeEditId.value) {
      await updateRoute(routeEditId.value, payload);
    } else {
      await createRoute(payload);
    }
    routeDialog.value = false;
    notice.value = t('logistics.route_saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

// --- Modes de livraison client (dialogue partagé avec « Modes de livraison ») ---
const deliveryDialog = ref(false);
const deliveryEditing = ref<ShippingRoute | null>(null);
function openDeliveryCreate() {
  deliveryEditing.value = null;
  deliveryDialog.value = true;
}
function openDeliveryEdit(r: ShippingRoute) {
  deliveryEditing.value = r;
  deliveryDialog.value = true;
}
async function onDeliverySaved() {
  notice.value = t('logistics.route_saved');
  await load();
}

onMounted(load);
</script>
