<template>
  <q-page padding>
    <div class="text-h6 q-mb-md">Trajets &amp; Lieux</div>
    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" rounded dense>{{
      notice
    }}</q-banner>

    <!-- Lieux -->
    <div class="row items-center q-mb-sm">
      <div class="text-subtitle1 text-weight-medium col">Lieux</div>
      <q-btn color="primary" icon="add" label="Nouveau lieu" no-caps @click="openPlaceCreate" />
    </div>
    <div class="text-caption text-grey-7 q-mb-sm">
      Entrepôts, ports, aéroports, îles… utilisés comme origine / destination des tronçons.
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
      <template #body-cell-warehouse="props">
        <q-td :props="props">
          <q-icon v-if="props.row.is_warehouse" name="check" color="positive" />
          <span v-else>—</span>
        </q-td>
      </template>
      <template #body-cell-customs="props">
        <q-td :props="props">
          <q-icon v-if="props.row.customs_clearance" name="check" color="positive" />
          <span v-else>—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openPlaceEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun lieu.</div>
      </template>
    </q-table>

    <!-- Trajets -->
    <div class="row items-center q-mt-lg q-mb-sm">
      <div class="text-subtitle1 text-weight-medium col">Trajets (tronçons)</div>
      <q-btn
        color="primary"
        icon="add"
        label="Nouveau trajet"
        no-caps
        :disable="places.length < 2"
        @click="openRouteCreate"
      />
    </div>
    <div class="text-caption text-grey-7 q-mb-sm">
      Tronçon réutilisable d'un lieu à un autre (fournisseur → entrepôt, entrepôt → client…).
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
          {{ placeName(props.row.from_place_id) }} → {{ placeName(props.row.to_place_id) }}
        </q-td>
      </template>
      <template #body-cell-to_customer="props">
        <q-td :props="props">
          <q-icon v-if="props.row.is_to_customer" name="check" color="positive" />
          <span v-else>—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openRouteEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucun trajet.</div>
      </template>
    </q-table>

    <!-- Place dialog -->
    <q-dialog v-model="placeDialog">
      <q-card style="min-width: 400px">
        <q-card-section class="text-h6">{{
          placeEditId ? 'Modifier le lieu' : 'Nouveau lieu'
        }}</q-card-section>
        <q-form @submit.prevent="submitPlace">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
              <q-input
                v-model="placeForm.country"
                label="Pays (ISO, ex: PF)"
                outlined
                dense
                bottom-slots
                class="col"
              />
            </div>
            <q-toggle v-model="placeForm.is_warehouse" label="Entrepôt" />
            <q-toggle v-model="placeForm.customs_clearance" label="Dédouanement" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              :label="placeEditId ? 'Enregistrer' : 'Créer'"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Route dialog -->
    <q-dialog v-model="routeDialog">
      <q-card style="min-width: 460px">
        <q-card-section class="text-h6">{{
          routeEditId ? 'Modifier le trajet' : 'Nouveau trajet'
        }}</q-card-section>
        <q-form @submit.prevent="submitRoute">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
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
import {
  createPlace,
  createRoute,
  listPlaces,
  listRoutes,
  updatePlace,
  updateRoute,
  type Place,
  type ShippingRoute,
} from 'src/api/logistics';
import { extractApiError } from 'src/api/errors';

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

const placeTypeOptions = [
  { label: 'Entrepôt', value: 'warehouse' },
  { label: 'Aéroport', value: 'airport' },
  { label: 'Port', value: 'seaport' },
  { label: 'Île', value: 'island' },
  { label: 'Adresse', value: 'address' },
];
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
  const used = routes.value
    .map((r) => r.last_leg_delivery_type)
    .filter((v): v is string => !!v);
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
function placeName(id: string): string {
  return placeById.value.get(id)?.name ?? id.slice(0, 8);
}

const placeColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'type', label: 'Type', field: 'type', align: 'left' },
  { name: 'code', label: 'Code', field: 'code', align: 'left' },
  { name: 'city', label: 'Ville', field: 'city', align: 'left' },
  { name: 'country', label: 'Pays', field: 'country', align: 'left' },
  { name: 'warehouse', label: 'Entrepôt', field: 'is_warehouse', align: 'center' },
  { name: 'customs', label: 'Douane', field: 'customs_clearance', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];
const routeColumns: QTableColumn[] = [
  { name: 'name', label: 'Nom', field: 'name', align: 'left' },
  { name: 'path', label: 'Trajet', field: 'from_place_id', align: 'left' },
  { name: 'mode', label: 'Mode', field: 'mode', align: 'left' },
  { name: 'service_level', label: 'Service', field: 'service_level', align: 'left' },
  { name: 'eta', label: 'Délai (j)', field: 'eta_days', align: 'left' },
  { name: 'price_per_kg', label: 'Prix/kg', field: 'price_per_kg', align: 'left' },
  { name: 'base_price', label: 'Forfait', field: 'base_price', align: 'left' },
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
  country: '',
  is_warehouse: true,
  customs_clearance: false,
});

function resetPlaceForm() {
  placeForm.name = '';
  placeForm.type = 'warehouse';
  placeForm.code = '';
  placeForm.city = '';
  placeForm.country = '';
  placeForm.is_warehouse = true;
  placeForm.customs_clearance = false;
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
  placeForm.country = p.country ?? '';
  placeForm.is_warehouse = p.is_warehouse;
  placeForm.customs_clearance = p.customs_clearance;
  placeDialog.value = true;
}

async function submitPlace() {
  saving.value = true;
  dialogError.value = null;
  const payload = {
    name: placeForm.name.trim(),
    type: placeForm.type,
    code: placeForm.code.trim() || null,
    city: placeForm.city.trim() || null,
    country: placeForm.country.trim().toUpperCase() || null,
    is_warehouse: placeForm.is_warehouse,
    customs_clearance: placeForm.customs_clearance,
  };
  try {
    if (placeEditId.value) {
      await updatePlace(placeEditId.value, payload);
    } else {
      await createPlace(payload);
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
  is_to_customer: boolean;
  last_leg_delivery_type: string | null;
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
  is_to_customer: false,
  last_leg_delivery_type: null,
});

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
  routeForm.is_to_customer = false;
  routeForm.last_leg_delivery_type = null;
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
  routeForm.is_to_customer = r.is_to_customer;
  routeForm.last_leg_delivery_type = r.last_leg_delivery_type;
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
    is_to_customer: routeForm.is_to_customer,
    last_leg_delivery_type: routeForm.is_to_customer
      ? routeForm.last_leg_delivery_type
      : null,
  };
  try {
    if (routeEditId.value) {
      await updateRoute(routeEditId.value, payload);
    } else {
      await createRoute(payload);
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
