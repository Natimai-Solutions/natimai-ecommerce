<template>
  <q-page class="admin-page">
    <PageHeader
      title="Trajets et lieux"
      hint="Lieux logistiques et tronçons tarifés qui composent les trajets de livraison."
    >
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

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <!-- Lieux -->
    <section class="app-section" aria-labelledby="places-title">
      <div class="app-section__head">
        <h2 id="places-title" class="app-section__title">Lieux</h2>
        <p class="app-section__hint">
          Entrepôts, ports, aéroports, îles… utilisés comme origine / destination des tronçons.
        </p>
        <q-btn
          class="app-section__action"
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau lieu"
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
              label="Principal"
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
                Définir comme entrepôt principal : les articles fournisseur y convergent et le
                dernier tronçon vers le client en part. L'ancien est déflaggé.
              </q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:pencil-simple" @click="openPlaceEdit(props.row)">
              <q-tooltip>Modifier</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">Aucun lieu.</div>
        </template>
      </q-table>
    </section>

    <!-- Trajets -->
    <section class="app-section" aria-labelledby="routes-title">
      <div class="app-section__head">
        <h2 id="routes-title" class="app-section__title">Trajets (tronçons)</h2>
        <p class="app-section__hint">
          Tronçon réutilisable d'un lieu à un autre (fournisseur → entrepôt, entrepôt → client…).
        </p>
        <q-btn
          class="app-section__action"
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouveau trajet"
          :disable="places.length < 2"
          @click="openRouteCreate"
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
              <q-tooltip>Modifier</q-tooltip>
            </q-btn>
          </q-td>
        </template>
        <template #no-data>
          <div class="full-width text-center text-subtle q-pa-md">Aucun trajet.</div>
        </template>
      </q-table>
    </section>

    <!-- Place dialog -->
    <q-dialog v-model="placeDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ placeEditId ? 'Modifier le lieu' : 'Nouveau lieu' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitPlace">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="placeForm.name"
              label="Nom *"
              outlined
              dense
              bottom-slots
              :rules="req"
            />
            <q-select
              v-model="placeForm.type"
              :options="placeTypeOptions"
              label="Type *"
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
              label="Zone parente (optionnel)"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              clearable
              hint="Ex. commune → île, île → archipel, boutique → commune."
            />
            <q-input
              v-model="placeForm.code"
              label="Code (IATA / LOCODE, optionnel)"
              outlined
              dense
              bottom-slots
            />
            <div class="row" style="gap: 8px">
              <q-input
                v-model="placeForm.city"
                label="Ville"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-select
                v-model="placeForm.country"
                :options="filteredCountryOptions"
                label="Pays"
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
            <q-select
              v-if="isGeoType(placeForm.type)"
              v-model="placePostalCodes"
              label="Codes postaux de la zone"
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
              hint="Tapez un code postal puis Entrée (ex. 98728). Sert à déduire la zone depuis l'adresse client. Pays requis."
            />
            <q-toggle v-model="placeForm.is_warehouse" label="Entrepôt" />
            <q-toggle v-model="placeForm.customs_clearance" label="Dédouanement" />
            <template v-if="!isGeoType(placeForm.type)">
              <q-select
                v-model="placeForm.customs_regime"
                :options="customsRegimeOptions"
                label="Régime douanier (lieu d'origine fournisseur)"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                hint="Automatique : même pays que l'entrepôt principal (ou pays exempté dans les réglages) = local, sinon import. Forcez si ce pays fait exception."
              />
              <q-toggle
                v-model="placeForm.dropship_enabled"
                label="Dropshipping : ce fournisseur livre directement le client"
              />
            </template>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="placeEditId ? 'Enregistrer' : 'Créer'"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Route dialog -->
    <q-dialog v-model="routeDialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ routeEditId ? 'Modifier le trajet' : 'Nouveau trajet' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitRoute">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="routeForm.name"
              label="Nom du trajet *"
              outlined
              dense
              bottom-slots
              :rules="req"
            />
            <div class="row" style="gap: 8px">
              <q-select
                v-model="routeForm.from_place_id"
                :options="placeOptions"
                label="Origine *"
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
                label="Destination *"
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
                label="Mode *"
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
                label="Niveau de service"
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
              label="Libellé client (optionnel)"
              outlined
              dense
              bottom-slots
            />
            <div class="row" style="gap: 8px">
              <q-input
                v-model.number="routeForm.eta_days"
                label="Délai (jours)"
                type="number"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-input
                v-model="routeForm.price_per_kg"
                label="Prix / kg (XPF)"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-input
                v-model="routeForm.base_price"
                label="Forfait (XPF)"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
            </div>
            <h3 class="admin-subtitle q-mt-sm q-mb-none">
              Grille par tranches de poids (optionnel)
            </h3>
            <div class="text-caption text-muted">
              Remplace « prix/kg × poids » : le prix de la première tranche dont le plafond couvre
              le poids taxable. Laissez le plafond vide pour une dernière tranche « et au-delà » ;
              sinon, l'excédent au-dessus de la dernière tranche est facturé au prix/kg. Le forfait
              s'ajoute.
            </div>
            <div
              v-for="(band, index) in routeBands"
              :key="index"
              class="row items-start"
              style="gap: 8px"
            >
              <q-input
                v-model="band.max_kg"
                label="Jusqu'à (kg)"
                type="number"
                step="0.001"
                outlined
                dense
                bottom-slots
                class="col"
                :hint="band.max_kg.trim() ? undefined : 'vide = et au-delà'"
              />
              <q-input
                v-model="band.price"
                label="Prix (XPF)"
                type="number"
                step="0.01"
                outlined
                dense
                bottom-slots
                class="col"
              />
              <q-btn
                flat
                dense
                round
                color="negative"
                icon="ph:trash"
                @click="routeBands.splice(index, 1)"
              >
                <q-tooltip>Retirer la tranche</q-tooltip>
              </q-btn>
            </div>
            <q-btn
              flat
              dense
              no-caps
              icon="ph:plus"
              label="Ajouter une tranche"
              @click="routeBands.push({ max_kg: '', price: '' })"
            />
            <q-input
              v-model="routeForm.free_shipping_threshold"
              label="Franco de port à partir de (XPF, valeur du panier)"
              type="number"
              step="0.01"
              outlined
              dense
              bottom-slots
              clearable
              hint="Ce tronçon devient gratuit dès que la valeur expédiée atteint ce montant. Vide = jamais gratuit."
            />
            <q-toggle v-model="routeForm.is_to_customer" label="Tronçon final (livraison client)" />
            <q-select
              v-if="routeForm.is_to_customer"
              v-model="routeForm.last_leg_delivery_type"
              :options="deliveryTypeSuggestions"
              label="Mode de livraison (last-leg)"
              outlined
              dense
              bottom-slots
              clearable
              use-input
              input-debounce="0"
              new-value-mode="add-unique"
              @filter="filterDeliveryTypes"
              hint="Choisissez un mode ou tapez-en un nouveau (ex. sea_freight), puis Entrée. Relie ce tronçon au choix client au checkout."
            />
            <q-toggle
              v-if="routeForm.is_to_customer"
              v-model="routeForm.always_available"
              label="Toujours proposé (quelle que soit la destination)"
            />
            <q-select
              v-if="routeForm.is_to_customer && !routeForm.always_available"
              v-model="routeServedPlaceIds"
              :options="geoPlaceOptions"
              label="Zones desservies"
              outlined
              dense
              bottom-slots
              multiple
              use-chips
              emit-value
              map-options
              hint="Îles, communes ou archipels desservis — une zone parente couvre toutes ses zones enfants. Vide = desservi partout (héritage)."
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="routeEditId ? 'Enregistrer' : 'Créer'"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { countryOptions, type CountryOption } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import {
  createPlace,
  createRoute,
  getPlacePostalCodes,
  getRouteServedPlaces,
  listPlaces,
  listRoutes,
  setPlacePostalCodes,
  setRouteServedPlaces,
  updatePlace,
  updateRoute,
  type Place,
  type ShippingRoute,
  setMainWarehouse,
} from '@/api/logistics';
import type { WeightBand } from '@/api/logistics';
import { extractApiError } from '@/api/errors';

const places = ref<Place[]>([]);
const routes = ref<ShippingRoute[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || 'Requis',
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

const placeTypeOptions = [
  { label: 'Entrepôt', value: 'warehouse' },
  { label: 'Aéroport', value: 'airport' },
  { label: 'Port', value: 'seaport' },
  { label: 'Boutique', value: 'shop' },
  { label: 'Pays', value: 'country' },
  { label: 'Région / Archipel', value: 'region' },
  { label: 'Île', value: 'island' },
  { label: 'Commune', value: 'municipality' },
  { label: 'Adresse', value: 'address' },
];
// Zones géographiques : forment l'arbre de desserte + portent les codes postaux.
const GEO_TYPES = ['country', 'region', 'island', 'municipality'];
function isGeoType(type: string): boolean {
  return GEO_TYPES.includes(type);
}
const modeOptions = [
  { label: 'Avion', value: 'air' },
  { label: 'Bateau', value: 'sea' },
  { label: 'Route', value: 'road' },
  { label: 'Retrait', value: 'pickup' },
];
const serviceLevelOptions = [
  { label: 'Rapide', value: 'rapide' },
  { label: 'Économique', value: 'economique' },
  { label: 'Écologique', value: 'ecologique' },
];
// Delivery modes are free-form: suggest a few defaults + every mode already used
// on a route, but let the admin type a new one (e.g. "sea_freight").
const deliveryTypeAll = computed<string[]>(() => {
  const defaults = ['pickup', 'home_delivery', 'air_freight', 'sea_freight'];
  const used = routes.value.map((r) => r.last_leg_delivery_type).filter((v): v is string => !!v);
  return Array.from(new Set([...defaults, ...used])).sort();
});
const deliveryTypeSuggestions = ref<string[]>([]);
function filterDeliveryTypes(val: string, update: (fn: () => void) => void) {
  update(() => {
    const needle = val.toLowerCase();
    deliveryTypeSuggestions.value = deliveryTypeAll.value.filter((o) =>
      o.toLowerCase().includes(needle),
    );
  });
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

const placeColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'type', label: 'Type', field: 'type', align: 'left' },
  { name: 'parent', label: 'Zone parente', field: 'parent_id', align: 'left' },
  { name: 'code', label: 'Code', field: 'code', align: 'left' },
  { name: 'city', label: 'Ville', field: 'city', align: 'left' },
  { name: 'country', label: 'Pays', field: 'country', align: 'left' },
  { name: 'warehouse', label: 'Entrepôt', field: 'is_warehouse', align: 'center' },
  { name: 'customs', label: 'Douane', field: 'customs_clearance', align: 'center' },
  { name: 'origin', label: 'Origine', field: 'customs_regime', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

const customsRegimeOptions = [
  { label: 'Automatique (selon le pays)', value: null },
  { label: 'Local — sans douane ni fret import', value: 'domestic' },
  { label: 'Import — douane et fret import', value: 'import' },
];

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
    notice.value = `${p.name} est désormais l'entrepôt principal.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Opération impossible.';
  }
}
const routeColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'path', label: 'Trajet', field: 'from_place_id', align: 'left' },
  { name: 'mode', label: 'Mode', field: 'mode', align: 'left' },
  { name: 'service_level', label: 'Service', field: 'service_level', align: 'left' },
  { name: 'eta', label: 'Délai (j)', field: 'eta_days', align: 'left' },
  { name: 'price_per_kg', label: 'Prix/kg', field: 'price_per_kg', align: 'left' },
  { name: 'base_price', label: 'Forfait', field: 'base_price', align: 'left' },
  { name: 'tariff', label: 'Grille / franco', field: 'weight_bands', align: 'left' },
  {
    name: 'delivery_mode',
    label: 'Mode last-leg',
    field: 'last_leg_delivery_type',
    align: 'left',
  },
  { name: 'to_customer', label: 'Final', field: 'is_to_customer', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [places.value, routes.value] = await Promise.all([listPlaces(), listRoutes()]);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
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
    dialogError.value = 'Le pays (ISO) est requis pour rattacher des codes postaux.';
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
    notice.value = 'Lieu enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

// --- Route create / edit ---
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
  last_leg_delivery_type: string | null;
  always_available: boolean;
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
  last_leg_delivery_type: null,
  always_available: false,
});
const routeServedPlaceIds = ref<string[]>([]);
// Weight grid rows edited as strings (q-input); serialized on submit.
const routeBands = ref<{ max_kg: string; price: string }[]>([]);

function bandsPayload(): WeightBand[] | null {
  const rows = routeBands.value
    .filter((b) => b.price.trim() !== '')
    .map((b) => ({ max_kg: b.max_kg.trim() || null, price: b.price.trim() }));
  return rows.length > 0 ? rows : null;
}

function tariffSummary(r: ShippingRoute): string {
  const parts: string[] = [];
  if (r.weight_bands && r.weight_bands.length > 0) {
    parts.push(`${r.weight_bands.length} tranche${r.weight_bands.length > 1 ? 's' : ''}`);
  }
  if (r.free_shipping_threshold) {
    parts.push(`franco ≥ ${r.free_shipping_threshold}`);
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
  routeForm.last_leg_delivery_type = null;
  routeForm.always_available = false;
  routeServedPlaceIds.value = [];
  routeBands.value = [];
}

function openRouteCreate() {
  dialogError.value = null;
  routeEditId.value = null;
  resetRouteForm();
  routeDialog.value = true;
}

function openRouteEdit(r: ShippingRoute) {
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
  routeBands.value = (r.weight_bands ?? []).map((b) => ({
    max_kg: b.max_kg ?? '',
    price: b.price,
  }));
  routeForm.is_to_customer = r.is_to_customer;
  routeForm.last_leg_delivery_type = r.last_leg_delivery_type;
  routeForm.always_available = r.always_available;
  routeServedPlaceIds.value = [];
  if (r.is_to_customer) {
    getRouteServedPlaces(r.id)
      .then((served) => {
        routeServedPlaceIds.value = served.map((p) => p.id);
      })
      .catch(() => {
        // Non bloquant : l'édition des autres champs reste possible.
      });
  }
  routeDialog.value = true;
}

async function submitRoute() {
  if (!routeForm.from_place_id || !routeForm.to_place_id) {
    dialogError.value = 'Origine et destination requises.';
    return;
  }
  if (routeForm.from_place_id === routeForm.to_place_id) {
    dialogError.value = "L'origine et la destination doivent être différentes.";
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
    weight_bands: bandsPayload(),
    // q-input clearable sets null; keep the payload a string or null.
    free_shipping_threshold: (routeForm.free_shipping_threshold ?? '').trim() || null,
    is_to_customer: routeForm.is_to_customer,
    last_leg_delivery_type: routeForm.is_to_customer ? routeForm.last_leg_delivery_type : null,
    always_available: routeForm.is_to_customer ? routeForm.always_available : false,
  };
  try {
    let saved: ShippingRoute;
    if (routeEditId.value) {
      saved = await updateRoute(routeEditId.value, payload);
    } else {
      saved = await createRoute(payload);
    }
    if (routeForm.is_to_customer) {
      await setRouteServedPlaces(
        saved.id,
        routeForm.always_available ? [] : routeServedPlaceIds.value,
      );
    }
    routeDialog.value = false;
    notice.value = 'Trajet enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
