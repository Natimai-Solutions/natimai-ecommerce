<template>
  <q-dialog v-model="open">
    <q-card class="app-dialog app-dialog--wide">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">
          {{ route ? $t('logistics.edit_delivery_mode') : $t('logistics.new_delivery_mode') }}
        </h2>
      </q-card-section>
      <q-form @submit.prevent="submit">
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
          <AppNotice v-if="!mainWarehouse" tone="warning" dense>
            {{ $t('logistics.no_main_warehouse') }}
          </AppNotice>

          <q-select
            v-model="preset"
            :options="presetOptions"
            :label="$t('logistics.delivery_mode')"
            outlined
            dense
            bottom-slots
            emit-value
            map-options
            :rules="req"
            @update:model-value="applyPreset"
          />
          <div v-if="preset === CUSTOM_DELIVERY" class="row" style="gap: 8px">
            <q-input
              v-model="customCode"
              :label="$t('logistics.custom_code')"
              outlined
              dense
              bottom-slots
              class="col"
              :rules="codeRules"
              :hint="$t('logistics.custom_code_hint')"
            />
            <q-select
              v-model="form.mode"
              :options="modeOptions"
              :label="$t('logistics.transport')"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              class="col-4"
              :rules="req"
            />
          </div>

          <!-- Retrait : le lieu dont le nom et l'adresse sont affichés au
               client au checkout. L'entrepôt principal convient (retrait sur
               place) ; « Nouveau lieu » en crée un sans passer par Lieux. -->
          <div v-if="isPickup" class="row items-start" style="gap: 8px">
            <q-select
              v-model="form.to_place_id"
              :options="pickupPlaceOptions"
              :label="$t('logistics.pickup_place')"
              outlined
              dense
              bottom-slots
              emit-value
              map-options
              class="col"
              :rules="req"
              :hint="pickupPlaceHint"
            />
            <q-btn
              flat
              no-caps
              icon="ph:plus"
              :label="$t('logistics.new_pickup_place')"
              class="q-mt-xs"
              @click="openPlaceCreate"
            />
          </div>

          <q-input
            v-model="form.customer_label"
            :label="$t('logistics.customer_label')"
            outlined
            dense
            bottom-slots
            :hint="$t('logistics.customer_label_hint')"
          />

          <div class="row" style="gap: 8px">
            <q-input
              v-model="form.base_price"
              :label="$t('logistics.price', { currency: shopConfig.currency })"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
              bottom-slots
              class="col"
              :hint="$t('logistics.price_hint')"
            />
            <q-input
              v-model="form.free_shipping_threshold"
              :label="$t('logistics.free_from_short', { currency: shopConfig.currency })"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
              bottom-slots
              clearable
              class="col"
              :hint="$t('logistics.free_hint_short')"
            />
            <q-input
              v-model.number="form.eta_days"
              :label="$t('logistics.eta')"
              type="number"
              min="0"
              outlined
              dense
              bottom-slots
              class="col-3"
            />
          </div>

          <q-expansion-item
            v-model="weightOpen"
            dense
            dense-toggle
            switch-toggle-side
            header-class="text-muted q-px-none"
            :label="$t('logistics.weight_pricing')"
          >
            <div class="text-caption text-muted q-mb-sm">
              {{ $t('logistics.weight_pricing_hint') }}
            </div>
            <q-input
              v-model="form.price_per_kg"
              :label="$t('logistics.per_kg', { currency: shopConfig.currency })"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
              bottom-slots
            />
            <WeightBandsEditor v-model="bands" :currency="shopConfig.currency" />
          </q-expansion-item>

          <div class="text-caption text-muted q-mt-sm">{{ $t('logistics.coverage') }}</div>
          <q-option-group v-model="coverage" :options="coverageOptions" inline dense />
          <q-select
            v-if="coverage === 'zones'"
            v-model="servedPlaceIds"
            :options="geoPlaceOptions"
            :label="$t('logistics.zones')"
            outlined
            dense
            bottom-slots
            multiple
            use-chips
            emit-value
            map-options
            :rules="[(v: string[]) => v.length > 0 || $t('logistics.zones_required')]"
            :hint="$t('logistics.zones_hint_short')"
          />

          <q-expansion-item
            dense
            dense-toggle
            switch-toggle-side
            header-class="text-muted q-px-none"
            :label="$t('logistics.advanced')"
          >
            <div class="text-caption text-muted q-mb-sm">
              {{ $t('logistics.advanced_hint') }}
            </div>
            <q-input
              v-model="form.name"
              :label="$t('logistics.internal_name')"
              outlined
              dense
              bottom-slots
              :hint="$t('logistics.internal_name_hint')"
            />
            <div class="row" style="gap: 8px">
              <q-select
                v-model="form.from_place_id"
                :options="placeOptions"
                :label="$t('logistics.from')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                class="col"
              />
              <q-select
                v-if="!isPickup"
                v-model="form.to_place_id"
                :options="placeOptions"
                :label="$t('logistics.to')"
                outlined
                dense
                bottom-slots
                emit-value
                map-options
                clearable
                class="col"
              />
            </div>
          </q-expansion-item>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="route ? $t('common.save') : $t('common.create')"
            :loading="saving"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>

  <!-- Nouveau lieu de retrait (boutique), rattaché au pays de la boutique. -->
  <q-dialog v-model="placeDialog">
    <q-card class="app-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">{{ $t('logistics.new_pickup_place') }}</h2>
      </q-card-section>
      <q-form @submit.prevent="submitPlace">
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="placeError" tone="error" dense>{{ placeError }}</AppNotice>
          <q-input
            v-model="placeForm.name"
            :label="$t('logistics.name')"
            outlined
            dense
            bottom-slots
            :rules="req"
            :hint="$t('logistics.pickup_name_hint')"
          />
          <q-input
            v-model="placeForm.address_line1"
            :label="$t('logistics.address1')"
            outlined
            dense
            bottom-slots
          />
          <q-input
            v-model="placeForm.address_line2"
            :label="$t('logistics.address2')"
            outlined
            dense
            bottom-slots
          />
          <div class="row" style="gap: 8px">
            <q-input
              v-model="placeForm.postal_code"
              :label="$t('logistics.postcode')"
              outlined
              dense
              bottom-slots
              class="col-4"
            />
            <q-input
              v-model="placeForm.city"
              :label="$t('logistics.city')"
              outlined
              dense
              bottom-slots
              class="col"
            />
          </div>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="$t('common.create')"
            :loading="savingPlace"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
/**
 * Création / édition d'un mode de livraison client (tronçon final typé).
 *
 * Partagé par « Modes de livraison » (toujours visible) et « Trajets et
 * lieux » (module). Le cas courant tient en trois champs — mode, prix,
 * desserte ; origine et destination sont déduites (entrepôt principal →
 * lieu de retrait ou zone desservie) et restent en options avancées.
 */
import { computed, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import WeightBandsEditor from '@/components/WeightBandsEditor.vue';
import {
  createPlace,
  createRoute,
  getRouteServedPlaces,
  setRouteServedPlaces,
  updateRoute,
  type Place,
  type ShippingRoute,
} from '@/api/logistics';
import { extractApiError } from '@/api/errors';
import { useShopConfigStore } from '@/stores/shopConfig';
import {
  CUSTOM_DELIVERY,
  DELIVERY_CODE_PATTERN,
  DELIVERY_PRESETS,
  presetOf,
} from '@/utils/deliveryModes';
import { bandRows, bandsPayload, type BandRow } from '@/utils/weightBands';

const props = defineProps<{
  /** Trajet édité ; null = création. */
  route: ShippingRoute | null;
  places: Place[];
}>();
const emit = defineEmits<{ saved: [route: ShippingRoute]; 'place-created': [place: Place] }>();
const open = defineModel<boolean>({ required: true });

const { t } = useI18n();
const shopConfig = useShopConfigStore();

const GEO_TYPES = ['country', 'region', 'island', 'municipality'];
const isGeo = (p: Place) => GEO_TYPES.includes(p.type);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];
const codeRules = [
  ...req,
  (v: string | null | undefined) =>
    DELIVERY_CODE_PATTERN.test(String(v ?? '').trim()) || t('logistics.code_invalid'),
];

// Lieux créés depuis ce dialogue, visibles avant que la page ne recharge.
const createdPlaces = ref<Place[]>([]);
const allPlaces = computed(() => {
  const known = new Set(props.places.map((p) => p.id));
  return [...props.places, ...createdPlaces.value.filter((p) => !known.has(p.id))];
});
const placeById = computed(() => new Map(allPlaces.value.map((p) => [p.id, p])));
const mainWarehouse = computed(() => allPlaces.value.find((p) => p.is_main_warehouse) ?? null);

function pathLabel(place: Place): string {
  const parts = [place.name];
  let current = place;
  for (let depth = 0; depth < 6 && current.parent_id; depth += 1) {
    const parent = placeById.value.get(current.parent_id);
    if (!parent) break;
    parts.push(parent.name);
    current = parent;
  }
  return parts.join(' ‹ ');
}
const placeOptions = computed(() =>
  allPlaces.value.map((p) => ({ label: `${p.name}${p.code ? ` (${p.code})` : ''}`, value: p.id })),
);
const geoPlaceOptions = computed(() =>
  allPlaces.value
    .filter(isGeo)
    .map((p) => ({ label: pathLabel(p), value: p.id }))
    .sort((a, b) => a.label.localeCompare(b.label)),
);
// Lieux où un client peut venir chercher son colis : les nœuds physiques,
// l'entrepôt principal en tête (retrait sur place).
const pickupPlaceOptions = computed(() =>
  allPlaces.value
    .filter((p) => !isGeo(p))
    .map((p) => ({
      label:
        (p.city ? `${p.name} — ${p.city}` : p.name) +
        (p.is_main_warehouse ? ` (${t('logistics.main_warehouse_tag')})` : ''),
      value: p.id,
      main: p.is_main_warehouse,
    }))
    .sort((a, b) => Number(b.main) - Number(a.main) || a.label.localeCompare(b.label)),
);

const modeOptions = computed(() => [
  { label: t('logistics.m_air'), value: 'air' },
  { label: t('logistics.m_sea'), value: 'sea' },
  { label: t('logistics.m_road'), value: 'road' },
  { label: t('logistics.m_pickup'), value: 'pickup' },
]);
const presetOptions = computed(() => [
  ...DELIVERY_PRESETS.map((p) => ({ label: t(`logistics.${p.key}`), value: p.value })),
  { label: t('logistics.dm_custom'), value: CUSTOM_DELIVERY },
]);
const coverageOptions = computed(() => [
  { label: t('logistics.coverage_all'), value: 'all' },
  { label: t('logistics.coverage_zones'), value: 'zones' },
]);

const form = reactive({
  name: '',
  from_place_id: null as string | null,
  to_place_id: null as string | null,
  mode: 'road',
  customer_label: '',
  eta_days: null as number | null,
  price_per_kg: '',
  base_price: '',
  free_shipping_threshold: '',
});
const preset = ref<string | null>('home_delivery');
const customCode = ref('');
const coverage = ref<'all' | 'zones'>('all');
const servedPlaceIds = ref<string[]>([]);
const bands = ref<BandRow[]>([]);
const weightOpen = ref(false);
const error = ref<string | null>(null);
const saving = ref(false);

const isPickup = computed(() => form.mode === 'pickup');

function applyPreset(value: string | null) {
  const found = presetOf(value);
  if (found) form.mode = found.mode;
  if (found?.value === 'pickup' && !form.to_place_id) {
    form.to_place_id = mainWarehouse.value?.id ?? null;
  }
}

function reset() {
  const r = props.route;
  error.value = null;
  form.name = r?.name ?? '';
  form.from_place_id = r?.from_place_id ?? mainWarehouse.value?.id ?? null;
  form.to_place_id = r?.to_place_id ?? null;
  form.mode = r?.mode ?? 'road';
  form.customer_label = r?.customer_label ?? '';
  form.eta_days = r?.eta_days ?? null;
  form.price_per_kg = r?.price_per_kg ?? '';
  form.base_price = r?.base_price ?? '';
  form.free_shipping_threshold = r?.free_shipping_threshold ?? '';
  bands.value = bandRows(r?.weight_bands);
  weightOpen.value = Number(r?.price_per_kg ?? 0) > 0 || bands.value.length > 0;
  const type = r?.last_leg_delivery_type ?? (r ? null : 'home_delivery');
  if (presetOf(type)) {
    preset.value = type;
    customCode.value = '';
  } else {
    preset.value = type ? CUSTOM_DELIVERY : null;
    customCode.value = type ?? '';
  }
  coverage.value = 'all';
  servedPlaceIds.value = [];
  // Sans zone desservie, un trajet est proposé partout (always_available ou
  // non) : seul un trajet rattaché à des zones est « certaines zones ».
  if (r) {
    getRouteServedPlaces(r.id)
      .then((served) => {
        servedPlaceIds.value = served.map((p) => p.id);
        coverage.value = served.length > 0 && !r.always_available ? 'zones' : 'all';
      })
      .catch(() => {
        // Non bloquant : l'édition des autres champs reste possible.
      });
  }
}

watch(open, (value) => {
  if (value) reset();
});

const pickupPlaceHint = computed(() => {
  const place = form.to_place_id ? placeById.value.get(form.to_place_id) : undefined;
  if (!place) return t('logistics.pickup_place_hint');
  const locality = [place.postal_code, place.city].filter((v) => !!v).join(' ');
  const summary = [place.address_line1, place.address_line2, locality]
    .filter((v): v is string => !!v && v.length > 0)
    .join(', ');
  return summary
    ? `${t('logistics.pickup_place_hint')} ${summary}`
    : t('logistics.pickup_no_address');
});

function deliveryType(): string | null {
  if (preset.value === CUSTOM_DELIVERY) return customCode.value.trim().toLowerCase() || null;
  return preset.value;
}

// Destination implicite d'une livraison (hors retrait) : la première zone
// desservie, sinon la zone racine de l'origine (le pays). Elle ne sert qu'au
// suivi (« Entrepôt → Tahiti ») ; la desserte réelle vient des zones.
function defaultDestination(): string | null {
  const origin = form.from_place_id;
  const served = servedPlaceIds.value.find((id) => id !== origin);
  if (coverage.value === 'zones' && served) return served;
  let current = origin ? placeById.value.get(origin) : undefined;
  let top: Place | undefined;
  for (let depth = 0; depth < 10 && current?.parent_id; depth += 1) {
    current = placeById.value.get(current.parent_id);
    if (current) top = current;
  }
  if (top && top.id !== origin) return top.id;
  return allPlaces.value.find((p) => isGeo(p) && !p.parent_id && p.id !== origin)?.id ?? null;
}

function defaultName(type: string): string {
  const label = form.customer_label.trim();
  if (label) return label;
  const found = presetOf(type);
  const base = found ? t(`logistics.${found.key}`) : type;
  const place = isPickup.value && form.to_place_id ? placeById.value.get(form.to_place_id) : null;
  return place ? `${base} — ${place.name}` : base;
}

async function submit() {
  const type = deliveryType();
  if (!type) {
    error.value = t('common.required');
    return;
  }
  if (!form.from_place_id) form.from_place_id = mainWarehouse.value?.id ?? null;
  if (!form.from_place_id) {
    error.value = t('logistics.no_main_warehouse');
    return;
  }
  if (isPickup.value) {
    // Retrait à l'origine même (entrepôt principal) : un tronçon sans
    // déplacement, accepté.
    if (!form.to_place_id) {
      error.value = t('logistics.pickup_place_required');
      return;
    }
  } else if (!form.to_place_id || form.to_place_id === form.from_place_id) {
    form.to_place_id = defaultDestination();
    if (!form.to_place_id) {
      error.value = t('logistics.dest_unresolved');
      return;
    }
  }
  if (coverage.value === 'zones' && servedPlaceIds.value.length === 0) {
    error.value = t('logistics.zones_required');
    return;
  }

  saving.value = true;
  error.value = null;
  const payload = {
    name: form.name.trim() || defaultName(type),
    from_place_id: form.from_place_id,
    to_place_id: form.to_place_id,
    mode: form.mode,
    service_level: null,
    customer_label: form.customer_label.trim() || null,
    // v-model.number leaves an empty field as "" at runtime — coerce to null.
    eta_days:
      typeof form.eta_days === 'number' && !Number.isNaN(form.eta_days) ? form.eta_days : null,
    price_per_kg: form.price_per_kg.trim() || null,
    base_price: form.base_price.trim() || null,
    weight_bands: bandsPayload(bands.value),
    free_shipping_threshold: (form.free_shipping_threshold ?? '').trim() || null,
    is_to_customer: true,
    last_leg_delivery_type: type,
    always_available: coverage.value === 'all',
  };
  try {
    const saved = props.route
      ? await updateRoute(props.route.id, payload)
      : await createRoute(payload);
    await setRouteServedPlaces(saved.id, coverage.value === 'all' ? [] : servedPlaceIds.value);
    open.value = false;
    emit('saved', saved);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

// --- Nouveau lieu de retrait ---
const placeDialog = ref(false);
const placeError = ref<string | null>(null);
const savingPlace = ref(false);
const placeForm = reactive({
  name: '',
  address_line1: '',
  address_line2: '',
  postal_code: '',
  city: '',
});

function openPlaceCreate() {
  placeError.value = null;
  Object.assign(placeForm, {
    name: '',
    address_line1: '',
    address_line2: '',
    postal_code: '',
    city: '',
  });
  placeDialog.value = true;
}

async function submitPlace() {
  // Rattaché au pays de l'entrepôt principal (ou à la première zone racine).
  const country = mainWarehouse.value?.country ?? null;
  const countryPlace =
    allPlaces.value.find((p) => p.type === 'country' && p.country === country) ??
    allPlaces.value.find((p) => p.type === 'country' && !p.parent_id);
  savingPlace.value = true;
  placeError.value = null;
  try {
    const place = await createPlace({
      name: placeForm.name.trim(),
      type: 'shop',
      address_line1: placeForm.address_line1.trim() || null,
      address_line2: placeForm.address_line2.trim() || null,
      postal_code: placeForm.postal_code.trim() || null,
      city: placeForm.city.trim() || null,
      country: country ?? countryPlace?.country ?? null,
      parent_id: countryPlace?.id ?? null,
      is_warehouse: false,
    });
    createdPlaces.value.push(place);
    form.to_place_id = place.id;
    placeDialog.value = false;
    emit('place-created', place);
  } catch (err) {
    placeError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    savingPlace.value = false;
  }
}
</script>
