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

    <!-- Aide : les trois notions de l'écran et ce qui se règle ailleurs. -->
    <HelpPanel :title="$t('logistics.help_title')" :items="helpItems" storage-key="logistics">
      {{ $t('logistics.help_modes') }}
      <router-link to="/delivery-modes" class="admin-link">{{
        $t('layout.nav.delivery_modes')
      }}</router-link>
    </HelpPanel>

    <div class="admin-toolbar">
      <q-btn-toggle
        v-model="view"
        no-caps
        unelevated
        toggle-color="primary"
        :options="viewOptions"
        data-testid="logistics-view"
      />
    </div>

    <!-- Zones de livraison : l'arbre géographique (pays → région → île →
         commune) qui porte les codes postaux et la desserte des modes. -->
    <section v-if="view === 'zones'" class="app-section" aria-labelledby="zones-title">
      <div class="app-section__head">
        <h2 id="zones-title" class="app-section__title">{{ $t('logistics.zones_title') }}</h2>
        <p class="app-section__hint">{{ $t('logistics.zones_section_hint') }}</p>
        <q-btn
          class="app-section__action"
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('logistics.new_zone')"
          @click="openPlaceCreate('zone')"
        />
      </div>
      <q-table
        :rows="zoneRows"
        :columns="zoneColumns"
        row-key="id"
        flat
        bordered
        :rows-per-page-options="[0]"
        hide-pagination
        :loading="loading"
      >
        <template #body-cell-name="props">
          <q-td :props="props">
            <span :style="{ paddingLeft: `${placeDepth(props.row) * 20}px` }">
              <q-icon
                v-if="placeDepth(props.row) > 0"
                name="ph:arrow-elbow-down-right"
                size="14px"
                class="text-subtle q-mr-xs"
              />{{ props.row.name }}
            </span>
          </q-td>
        </template>
        <template #body-cell-type="props">
          <q-td :props="props">{{ placeTypeLabel(props.row.type) }}</q-td>
        </template>
        <template #body-cell-code="props">
          <q-td :props="props" class="font-mono">{{ props.row.code ?? '' }}</q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" align="right">
            <q-btn flat round dense icon="ph:pencil-simple" @click="openPlaceEdit(props.row)">
              <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">
            {{ $t('logistics.no_zone') }}
          </div>
        </template>
      </q-table>
    </section>

    <!-- Lieux logistiques : entrepôts, boutiques, ports, fournisseurs… -->
    <section v-if="view === 'places'" class="app-section" aria-labelledby="places-title">
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
          @click="openPlaceCreate('node')"
        />
      </div>
      <q-table
        :rows="nodeRows"
        :columns="placeColumns"
        row-key="id"
        flat
        bordered
        :rows-per-page-options="[0]"
        hide-pagination
        :loading="loading"
      >
        <template #body-cell-name="props">
          <q-td :props="props">
            <div class="text-weight-medium">{{ props.row.name }}</div>
            <div v-if="props.row.code" class="text-caption text-muted font-mono">
              {{ props.row.code }}
            </div>
          </q-td>
        </template>
        <template #body-cell-type="props">
          <q-td :props="props">{{ placeTypeLabel(props.row.type) }}</q-td>
        </template>
        <template #body-cell-location="props">
          <q-td :props="props">
            <div>{{ placeLocality(props.row) || '—' }}</div>
            <div v-if="props.row.parent_id" class="text-caption text-muted">
              {{ $t('logistics.in_zone', { zone: placeName(props.row.parent_id) }) }}
            </div>
          </q-td>
        </template>
        <template #body-cell-roles="props">
          <q-td :props="props">
            <div class="place-roles">
              <StatusTag
                v-for="tag in placeTags(props.row)"
                :key="tag.key"
                :label="tag.label"
                :tone="tag.tone"
                :icon="tag.icon"
              />
              <span v-if="placeTags(props.row).length === 0">—</span>
            </div>
          </q-td>
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
    <section v-if="view === 'routes'" class="app-section" aria-labelledby="routes-title">
      <div class="app-section__head">
        <h2 id="routes-title" class="app-section__title">{{ $t('logistics.routes') }}</h2>
        <p class="app-section__hint">
          {{ $t('logistics.routes_hint') }}
        </p>
        <div class="app-section__action row no-wrap" style="gap: 8px">
          <q-btn
            flat
            no-caps
            icon="ph:package"
            :label="$t('logistics.new_delivery_mode')"
            @click="openDeliveryCreate"
          />
          <q-btn
            color="primary"
            unelevated
            no-caps
            icon="ph:plus"
            :label="$t('logistics.new_route')"
            :disable="places.length < 2"
            @click="openRouteCreate"
          />
        </div>
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
        <template #body-cell-name="props">
          <q-td :props="props" class="cell-wrap">
            <div class="text-weight-medium">{{ props.row.name }}</div>
            <div class="text-caption text-muted">{{ routeTransportSummary(props.row) }}</div>
          </q-td>
        </template>
        <template #body-cell-path="props">
          <q-td :props="props" class="cell-wrap">
            {{ placeName(props.row.from_place_id) }}
            <q-icon name="ph:arrow-right" size="14px" class="text-subtle" />
            {{ placeName(props.row.to_place_id) }}
          </q-td>
        </template>
        <template #body-cell-tariff="props">
          <q-td :props="props">
            <div class="font-mono">{{ routePriceSummary(props.row) }}</div>
            <div v-if="props.row.free_shipping_threshold" class="text-caption text-muted">
              {{ $t('logistics.free_ge', { amount: props.row.free_shipping_threshold }) }}
            </div>
          </q-td>
        </template>
        <template #body-cell-customer="props">
          <q-td :props="props">
            <StatusTag
              v-if="props.row.is_to_customer && props.row.last_leg_delivery_type"
              :label="deliveryTypeLabel(props.row.last_leg_delivery_type, t)"
              tone="ok"
              icon="ph:package"
            />
            <StatusTag
              v-else-if="props.row.is_to_customer"
              :label="$t('logistics.tag_final')"
              tone="neutral"
            />
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
            {{
              placeKind === 'zone'
                ? placeEditId
                  ? $t('logistics.edit_zone')
                  : $t('logistics.new_zone')
                : placeEditId
                  ? $t('logistics.edit_place')
                  : $t('logistics.new_place_title')
            }}
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
              :options="placeKind === 'zone' ? zoneTypeOptions : nodeTypeOptions"
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
              :hint="
                placeKind === 'zone'
                  ? $t('logistics.parent_hint_zone')
                  : $t('logistics.parent_hint_node')
              "
            />
            <q-input
              v-model="placeForm.code"
              :label="placeKind === 'zone' ? $t('logistics.code_zone') : $t('logistics.code')"
              outlined
              dense
              bottom-slots
            />
            <div class="row" style="gap: 8px">
              <q-input
                v-if="placeKind === 'node'"
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
            <template v-if="placeKind === 'node'">
              <q-toggle v-model="placeForm.is_warehouse" :label="$t('logistics.warehouse')" />
              <q-toggle v-model="placeForm.customs_clearance" :label="$t('logistics.clearance')" />
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
import { useRoute, useRouter } from 'vue-router';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { countryOptions, type CountryOption } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import HelpPanel, { type HelpItem } from '@/components/HelpPanel.vue';
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

// Zones (desserte, codes postaux) et lieux (nœuds physiques) partagent le
// modèle Place mais pas l'écran : deux listes, deux formulaires.
const zoneTypeOptions = computed(() => [
  { label: t('logistics.pt_country'), value: 'country' },
  { label: t('logistics.pt_region'), value: 'region' },
  { label: t('logistics.pt_island'), value: 'island' },
  { label: t('logistics.pt_municipality'), value: 'municipality' },
]);
const nodeTypeOptions = computed(() => [
  { label: t('logistics.pt_warehouse'), value: 'warehouse' },
  { label: t('logistics.pt_shop'), value: 'shop' },
  { label: t('logistics.pt_airport'), value: 'airport' },
  { label: t('logistics.pt_port'), value: 'seaport' },
  { label: t('logistics.pt_supplier'), value: 'supplier' },
  { label: t('logistics.pt_address'), value: 'address' },
]);
function placeTypeLabel(type: string): string {
  return (
    [...zoneTypeOptions.value, ...nodeTypeOptions.value].find((o) => o.value === type)?.label ??
    type
  );
}

// Vue affichée (Trajets / Lieux / Zones), mémorisée dans l'URL.
type LogisticsView = 'routes' | 'places' | 'zones';
const VIEWS: LogisticsView[] = ['routes', 'places', 'zones'];
const currentRoute = useRoute();
const router = useRouter();
const view = computed<LogisticsView>({
  get: () => {
    const q = currentRoute.query.view;
    return typeof q === 'string' && (VIEWS as string[]).includes(q)
      ? (q as LogisticsView)
      : 'routes';
  },
  set: (value) => {
    void router.replace({ query: { ...currentRoute.query, view: value } });
  },
});
const viewOptions = computed(() => [
  { label: t('logistics.view_routes', { n: routes.value.length }), value: 'routes' },
  { label: t('logistics.view_places', { n: nodeRows.value.length }), value: 'places' },
  { label: t('logistics.view_zones', { n: zoneRows.value.length }), value: 'zones' },
]);

// Aide : les trois notions de l'écran.
const helpItems = computed<HelpItem[]>(() =>
  [
    { key: 'zones', icon: 'ph:map-trifold' },
    { key: 'places', icon: 'ph:warehouse' },
    { key: 'routes', icon: 'ph:path' },
  ].map(({ key, icon }) => ({
    icon,
    title: t(`logistics.help_${key}_title`),
    text: t(`logistics.help_${key}`),
  })),
); // Zones géographiques : forment l'arbre de desserte + portent les codes postaux.
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
function serviceLevelLabel(level: string | null): string {
  if (!level) return '—';
  return serviceLevelOptions.value.find((o) => o.value === level)?.label ?? level;
}
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

// Zones triées selon l'arbre (pays, puis ses régions, puis leurs îles…).
function placeDepth(place: Place): number {
  let depth = 0;
  let current = place;
  while (current.parent_id && depth < 10) {
    const parent = placeById.value.get(current.parent_id);
    if (!parent) break;
    depth += 1;
    current = parent;
  }
  return depth;
}
function rootPath(place: Place): string {
  return placePathLabel(place).split(' ‹ ').reverse().join(' › ');
}
const zoneRows = computed(() =>
  places.value
    .filter((p) => isGeoType(p.type))
    .sort((a, b) => rootPath(a).localeCompare(rootPath(b))),
);
const nodeRows = computed(() => places.value.filter((p) => !isGeoType(p.type)));
const zoneColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('logistics.col_name'), field: 'name', align: 'left' },
  { name: 'type', label: t('logistics.col_type'), field: 'type', align: 'left' },
  { name: 'code', label: t('logistics.col_code'), field: 'code', align: 'left' },
  { name: 'country', label: t('logistics.col_country'), field: 'country', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

// Cinq colonnes : code sous le nom, zone sous la ville, et les rôles du
// lieu (entrepôt, douane, origine, dropshipping) réunis en étiquettes — le
// tableau tient sans défilement horizontal.
const placeColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('logistics.col_name'), field: 'name', align: 'left' },
  { name: 'type', label: t('logistics.col_type'), field: 'type', align: 'left' },
  { name: 'location', label: t('logistics.col_location'), field: 'city', align: 'left' },
  { name: 'roles', label: t('logistics.col_roles'), field: 'is_warehouse', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

const customsRegimeOptions = computed(() => [
  { label: t('logistics.r_auto'), value: null },
  { label: t('logistics.r_local'), value: 'domestic' },
  { label: t('logistics.r_import'), value: 'import' },
]);

function placeLocality(p: Place): string {
  return [p.city, p.country].filter((v): v is string => !!v).join(', ');
}

interface PlaceTag {
  key: string;
  label: string;
  tone: 'ok' | 'neutral';
  icon?: string;
}
function placeTags(p: Place): PlaceTag[] {
  const tags: PlaceTag[] = [];
  if (p.is_main_warehouse) {
    tags.push({ key: 'main', label: t('logistics.main'), tone: 'ok', icon: 'ph:star' });
  } else if (p.is_warehouse) {
    tags.push({ key: 'warehouse', label: t('logistics.pt_warehouse'), tone: 'neutral' });
  }
  if (p.customs_clearance) {
    tags.push({ key: 'customs', label: t('logistics.tag_customs'), tone: 'neutral' });
  }
  if (p.customs_regime === 'domestic') {
    tags.push({ key: 'regime', label: t('logistics.tag_local'), tone: 'neutral' });
  } else if (p.customs_regime === 'import') {
    tags.push({ key: 'regime', label: t('logistics.tag_import'), tone: 'neutral' });
  }
  if (p.dropship_enabled) {
    tags.push({ key: 'dropship', label: t('logistics.tag_dropship'), tone: 'neutral' });
  }
  return tags;
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
// Cinq colonnes : transport, service et délai sous le nom, franco sous le
// tarif, et
// le rôle client (mode de livraison ou tronçon final) en étiquette — le
// tableau tient sans défilement horizontal.
const routeColumns = computed<QTableColumn[]>(() => [
  { name: 'name', label: t('logistics.col_name'), field: 'name', align: 'left' },
  { name: 'path', label: t('logistics.col_path'), field: 'from_place_id', align: 'left' },
  { name: 'tariff', label: t('logistics.col_tariff'), field: 'base_price', align: 'left' },
  {
    name: 'customer',
    label: t('logistics.col_customer'),
    field: 'last_leg_delivery_type',
    align: 'left',
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
const placeKind = computed<'zone' | 'node'>(() => (isGeoType(placeForm.type) ? 'zone' : 'node'));

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

function openPlaceCreate(kind: 'zone' | 'node') {
  dialogError.value = null;
  placeEditId.value = null;
  resetPlaceForm();
  if (kind === 'zone') {
    // Une commune, le plus souvent ; pays repris de la zone racine.
    placeForm.type = 'municipality';
    placeForm.is_warehouse = false;
    placeForm.country = zoneRows.value.find((z) => !z.parent_id)?.country ?? null;
  }
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

function routeTransportSummary(r: ShippingRoute): string {
  return [
    modeLabel(r.mode),
    r.service_level ? serviceLevelLabel(r.service_level) : null,
    r.eta_days != null ? t('delivery_modes.days', { n: r.eta_days }) : null,
  ]
    .filter((v): v is string => !!v)
    .join(' · ');
}

// Forfait + prix au kg + grille ; rien de tarifé = gratuit.
function routePriceSummary(r: ShippingRoute): string {
  const parts: string[] = [];
  if (Number(r.base_price ?? 0) > 0) parts.push(r.base_price ?? '');
  if (Number(r.price_per_kg ?? 0) > 0) parts.push(`${r.price_per_kg}/kg`);
  const n = r.weight_bands?.length ?? 0;
  if (n > 0) parts.push(t('delivery_modes.bands', { n }, n));
  return parts.length > 0 ? parts.join(' + ') : t('delivery_modes.free');
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

<style scoped lang="scss">
// q-table ne coupe pas les cellules : les noms et trajets longs passent à
// la ligne plutôt que d'élargir le tableau.
.cell-wrap {
  white-space: normal;
  min-width: 140px;
}

.place-roles {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
