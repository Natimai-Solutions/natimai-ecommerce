<template>
  <section class="app-section">
    <div class="app-section__head">
      <h2 class="app-section__title">Adresses</h2>
      <p class="app-section__hint">
        Utilisables tout de suite au paiement. Notre équipe les vérifie pour préparer la livraison.
      </p>
      <q-btn
        unelevated
        color="primary"
        icon="ph:plus"
        label="Ajouter une adresse"
        class="app-section__action"
        @click="openAddressDialog()"
      />
    </div>

    <AppNotice v-if="addressesError" tone="error" class="q-mb-md">
      {{ addressesError }}
    </AppNotice>

    <div v-if="loadingAddresses" class="address-grid" aria-busy="true">
      <q-skeleton v-for="n in 2" :key="n" height="148px" class="address-card__skeleton" />
    </div>

    <div v-else-if="addresses.length === 0" class="app-empty">
      <q-icon name="ph:map-pin" size="36px" class="text-subtle" />
      <h3>Aucune adresse enregistrée</h3>
      <p>Ajoutez une adresse de livraison pour aller plus vite au moment de commander.</p>
    </div>

    <ul v-else class="address-grid">
      <li v-for="address in addresses" :key="address.id" class="address-card">
        <div class="address-card__head">
          <span class="address-card__type">{{ typeLabel(address.type) }}</span>
          <StatusTag
            :tone="address.is_validated ? 'ok' : 'neutral'"
            :icon="address.is_validated ? 'ph:seal-check' : 'ph:clock'"
            :label="address.is_validated ? 'Vérifiée' : 'En cours de vérification'"
          />
        </div>
        <address class="address-card__body">
          {{ address.street }}<br />
          {{ address.postal_code }} {{ address.city }}<br />
          <template v-if="address.state">{{ address.state }}<br /></template>
          {{ countryLabel(address.country) }}
        </address>
        <div class="address-card__actions">
          <button type="button" class="text-link" @click="openAddressDialog(address)">
            Modifier
          </button>
          <button type="button" class="text-link" @click="confirmDelete(address)">Supprimer</button>
        </div>
      </li>
    </ul>

    <!-- ====================== Create / edit address dialog ====================== -->
    <q-dialog v-model="addressDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editingId ? "Modifier l'adresse" : 'Nouvelle adresse' }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="saveAddress">
          <q-card-section class="q-pt-none">
            <AppNotice v-if="dialogError" dense tone="error" class="q-mb-md">
              {{ dialogError }}
            </AppNotice>
            <q-select
              v-model="addressForm.type"
              :options="addressTypeOptions"
              label="Type *"
              emit-value
              map-options
              outlined
              dense
              class="q-mb-sm"
            />
            <q-select
              v-model="addressForm.country"
              :options="filteredCountryOptions"
              label="Pays *"
              outlined
              dense
              class="q-mb-sm"
              emit-value
              map-options
              use-input
              input-debounce="0"
              :rules="[(v) => !!v || 'Champ requis']"
              @filter="filterCountries"
            />
            <div class="row q-col-gutter-sm">
              <q-select
                v-model="addressForm.postal_code"
                :options="filteredPostalOptions"
                label="Code postal *"
                outlined
                dense
                class="col-5"
                emit-value
                map-options
                use-input
                fill-input
                hide-selected
                input-debounce="0"
                :disable="!countryChosen"
                :hide-dropdown-icon="postalDirectory.length === 0"
                :rules="[(v) => !!v || 'Requis']"
                @filter="filterPostalCodes"
                @input-value="onPostalTyped"
              >
                <template #option="scope">
                  <q-item v-bind="scope.itemProps">
                    <q-item-section>
                      <q-item-label>{{ scope.opt.value }}</q-item-label>
                      <q-item-label caption>{{ scope.opt.zone }}</q-item-label>
                    </q-item-section>
                  </q-item>
                </template>
              </q-select>
              <q-input
                v-model="addressForm.city"
                :label="cityRequired ? 'Ville *' : 'Ville'"
                outlined
                dense
                class="col-7"
                :disable="!postalFilled"
                :rules="cityRules"
              />
            </div>
            <q-input
              v-model="addressForm.street"
              label="Adresse (rue) *"
              outlined
              dense
              class="q-mb-sm"
              :disable="!postalFilled"
              :rules="[(v) => !!v || 'Champ requis']"
            />
            <q-input
              v-model="addressForm.state"
              label="État / Région / Île"
              outlined
              dense
              class="q-mb-sm"
              :disable="!postalFilled"
            />
            <AppNotice
              v-if="detectedZoneLabel"
              dense
              tone="success"
              icon="ph:map-pin"
              class="q-mt-sm"
            >
              Zone de livraison détectée : {{ detectedZoneLabel }}
            </AppNotice>
            <template v-else-if="zoneLookupDone && zoneOptions.length > 0">
              <AppNotice dense tone="warning" class="q-mt-sm q-mb-sm">
                Code postal non reconnu. Indiquez votre île ou zone de livraison.
              </AppNotice>
              <q-select
                v-model="manualPlaceId"
                :options="zoneOptions"
                label="Île / zone de livraison"
                outlined
                dense
                emit-value
                map-options
                clearable
              />
            </template>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              unelevated
              color="primary"
              :label="editingId ? 'Enregistrer' : 'Créer'"
              :loading="savingAddress"
              :disable="savingAddress || !postalFilled"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- ========================== Delete confirmation ========================== -->
    <q-dialog v-model="deleteDialog">
      <q-card class="app-dialog app-dialog--narrow">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">Supprimer cette adresse ?</h2>
          <p class="app-dialog__text">Elle ne sera plus proposée au moment de la commande.</p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat label="Annuler" v-close-popup />
          <q-btn
            flat
            label="Supprimer"
            color="negative"
            :loading="deleting"
            @click="performDelete"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { countryLabel, countryOptions, type CountryOption } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import {
  createMyAddress,
  deleteMyAddress,
  getGeoTree,
  listMyAddresses,
  listPostalCodes,
  resolvePostalZone,
  updateMyAddress,
  type Address,
  type AddressInput,
  type AddressType,
  type PlaceSummary,
  type PlaceTreeNode,
} from '@/api/addresses';
import { apiErrorMessage } from '@/utils/errors';

const addressTypeOptions = [
  { label: 'Livraison', value: 'shipping' },
  { label: 'Facturation', value: 'billing' },
  { label: 'Autre', value: 'other' },
];

function typeLabel(type: string): string {
  return addressTypeOptions.find((o) => o.value === type)?.label ?? type;
}

const loadingAddresses = ref(true);
const addressesError = ref<string | null>(null);
const addresses = ref<Address[]>([]);

const addressDialog = ref(false);
const editingId = ref<string | null>(null);
const savingAddress = ref(false);
const dialogError = ref<string | null>(null);
const addressForm = reactive<AddressInput>({
  street: '',
  city: '',
  state: '',
  postal_code: '',
  country: '',
  type: 'shipping',
});

const deleteDialog = ref(false);
const deleting = ref(false);
const addressToDelete = ref<Address | null>(null);

// --- Pays : sélecteur ISO (PF/FR épinglés), filtrable à la saisie -----------
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

/** Legacy addresses may store a free-text country ("Polynésie française"). */
function normalizeCountry(raw: string): string {
  const trimmed = raw.trim();
  if (/^[A-Za-z]{2}$/.test(trimmed)) return trimmed.toUpperCase();
  const match = allCountryOptions.find((o) =>
    o.label.toLowerCase().startsWith(trimmed.toLowerCase()),
  );
  return match?.value ?? trimmed;
}

// --- Code postal : autocomplete sur l'annuaire des codes connus -------------
// Sélectionner un code = sélectionner sa zone (l'île s'affiche en légende) ;
// la saisie reste libre pour les codes non répertoriés.
interface PostalOption {
  label: string;
  value: string;
  zone: string;
}
const postalDirectory = ref<PostalOption[]>([]);
const postalDirectoryCountry = ref<string | null>(null);
const filteredPostalOptions = ref<PostalOption[]>([]);

async function loadPostalDirectory(rawCountry: string): Promise<void> {
  const country = rawCountry.trim().toUpperCase();
  if (country.length !== 2) {
    postalDirectory.value = [];
    postalDirectoryCountry.value = null;
    return;
  }
  if (postalDirectoryCountry.value === country) return;
  try {
    const entries = await listPostalCodes(country);
    postalDirectory.value = entries.map((e) => ({
      label: e.postal_code,
      value: e.postal_code,
      zone: e.place_name,
    }));
    postalDirectoryCountry.value = country;
  } catch {
    // Annuaire indisponible : le champ reste une saisie libre classique.
    postalDirectory.value = [];
    postalDirectoryCountry.value = null;
  }
}

function filterPostalCodes(val: string, update: (fn: () => void) => void) {
  update(() => {
    const needle = val.trim().toLowerCase();
    // Matche le début du code OU le nom de la zone ("moo" → 98728 Moorea).
    filteredPostalOptions.value = needle
      ? postalDirectory.value.filter(
          (o) => o.value.startsWith(needle) || o.zone.toLowerCase().includes(needle),
        )
      : postalDirectory.value;
  });
}

function onPostalTyped(val: string) {
  addressForm.postal_code = val;
}

watch(
  () => addressForm.country,
  (country, previous) => {
    if (!addressDialog.value) return;
    // Changer de pays invalide le code postal et tout ce qui en découlait :
    // le formulaire redémarre à l'étape « code postal ».
    if (previous && country !== previous) {
      addressForm.postal_code = '';
      clearZoneAutofill();
    }
    if (country) void loadPostalDirectory(country);
  },
);

// --- Saisie progressive : Pays → Code postal → le reste ---------------------
const countryChosen = computed(() => addressForm.country.trim().length === 2);
const postalFilled = computed(() => addressForm.postal_code.trim().length > 0);

// --- Zone de livraison (île) : déduite du code postal, fallback manuel ------
const detectedZoneLabel = ref<string | null>(null);
const zoneLookupDone = ref(false);
const manualPlaceId = ref<string | null>(null);

// La ville n'est exigée que si le code postal ne suffit pas à situer la
// livraison (code inconnu et aucune île choisie à la main).
const cityRequired = computed(() => !detectedZoneLabel.value && !manualPlaceId.value);
const cityRules = computed(() =>
  cityRequired.value ? [(v: string) => !!v?.trim() || 'Requis : code postal non reconnu'] : [],
);

// Valeurs posées par l'auto-remplissage : on ne les efface / remplace que si
// l'utilisateur ne les a pas retouchées entre-temps.
let lastAutoCity: string | null = null;
let lastAutoState: string | null = null;

function clearZoneAutofill(): void {
  if (lastAutoCity && addressForm.city === lastAutoCity) addressForm.city = '';
  if (lastAutoState && addressForm.state === lastAutoState) addressForm.state = '';
  lastAutoCity = null;
  lastAutoState = null;
}

function applyZoneAutofill(place: PlaceSummary, ancestors: PlaceSummary[]): void {
  if (place.type === 'municipality') {
    // Commune → la ville est connue ; l'île / région vient de la hiérarchie.
    addressForm.city = place.name;
    lastAutoCity = place.name;
    const geo =
      ancestors.find((a) => a.type === 'island') ?? ancestors.find((a) => a.type === 'region');
    if (geo) {
      addressForm.state = geo.name;
      lastAutoState = geo.name;
    }
  } else if (place.type === 'island' || place.type === 'region') {
    if (lastAutoCity && addressForm.city === lastAutoCity) addressForm.city = '';
    lastAutoCity = null;
    addressForm.state = place.name;
    lastAutoState = place.name;
  }
}
const zoneOptions = ref<{ label: string; value: string }[]>([]);
const zoneTreeCountry = ref<string | null>(null);
let zoneLookupTimer: ReturnType<typeof setTimeout> | null = null;

function flattenZoneTree(nodes: PlaceTreeNode[], path: string[] = []): void {
  for (const node of nodes) {
    // Seules les zones fines sont sélectionnables (une île, pas tout un pays).
    if (node.type === 'island' || node.type === 'municipality') {
      const context = path.length > 0 ? ` (${path[path.length - 1]})` : '';
      zoneOptions.value.push({ label: `${node.name}${context}`, value: node.id });
    }
    flattenZoneTree(node.children, [...path, node.name]);
  }
}

async function loadZoneOptions(country: string): Promise<void> {
  if (zoneTreeCountry.value === country) return;
  zoneOptions.value = [];
  try {
    const roots = await getGeoTree(country);
    flattenZoneTree(roots);
    zoneOptions.value.sort((a, b) => a.label.localeCompare(b.label));
    zoneTreeCountry.value = country;
  } catch {
    // Pas d'arbre pour ce pays → pas de sélecteur (champ purement optionnel).
    zoneTreeCountry.value = null;
  }
}

async function lookupZone(autofill = true): Promise<void> {
  const country = addressForm.country.trim().toUpperCase();
  const postalCode = addressForm.postal_code.trim();
  detectedZoneLabel.value = null;
  zoneLookupDone.value = false;
  if (country.length !== 2 || postalCode.length === 0) return;
  try {
    const result = await resolvePostalZone(country, postalCode);
    if (result.place) {
      const context = result.ancestors[0] ? ` (${result.ancestors[0].name})` : '';
      detectedZoneLabel.value = `${result.place.name}${context}`;
      manualPlaceId.value = null;
      if (autofill) applyZoneAutofill(result.place, result.ancestors);
    } else {
      if (autofill) clearZoneAutofill();
      await loadZoneOptions(country);
    }
    zoneLookupDone.value = true;
  } catch {
    // Résolution indisponible : l'adresse reste enregistrable sans zone.
    zoneLookupDone.value = false;
  }
}

watch(
  () => [addressForm.postal_code, addressForm.country],
  () => {
    if (!addressDialog.value) return;
    if (zoneLookupTimer) clearTimeout(zoneLookupTimer);
    zoneLookupTimer = setTimeout(() => void lookupZone(), 400);
  },
);

async function loadAddresses() {
  loadingAddresses.value = true;
  addressesError.value = null;
  try {
    addresses.value = await listMyAddresses();
  } catch (err) {
    addressesError.value = apiErrorMessage(err) ?? 'Impossible de charger vos adresses.';
  } finally {
    loadingAddresses.value = false;
  }
}

function openAddressDialog(address?: Address) {
  dialogError.value = null;
  detectedZoneLabel.value = null;
  zoneLookupDone.value = false;
  manualPlaceId.value = null;
  lastAutoCity = null;
  lastAutoState = null;
  if (address) {
    editingId.value = address.id;
    addressForm.street = address.street;
    addressForm.city = address.city;
    addressForm.state = address.state ?? '';
    addressForm.postal_code = address.postal_code;
    addressForm.country = normalizeCountry(address.country);
    addressForm.type = (address.type as AddressType) ?? 'shipping';
    manualPlaceId.value = address.place_id;
    void loadPostalDirectory(addressForm.country);
    // Pas d'auto-remplissage à l'ouverture : on n'écrase pas ce que le client
    // avait enregistré ; seul un changement de code postal re-remplit.
    void lookupZone(false);
  } else {
    editingId.value = null;
    addressForm.street = '';
    addressForm.city = '';
    addressForm.state = '';
    addressForm.postal_code = '';
    // Marché principal : le dropdown des codes postaux marche dès l'ouverture.
    addressForm.country = 'PF';
    addressForm.type = 'shipping';
    void loadPostalDirectory(addressForm.country);
  }
  addressDialog.value = true;
}

async function saveAddress() {
  savingAddress.value = true;
  dialogError.value = null;
  try {
    const payload: AddressInput = {
      street: addressForm.street,
      city: addressForm.city,
      state: addressForm.state?.trim() ? addressForm.state : null,
      postal_code: addressForm.postal_code,
      country: addressForm.country,
      type: addressForm.type,
    };
    // Zone choisie à la main (code postal non reconnu) : envoyée explicitement.
    // Sinon on laisse le backend déduire la zone du code postal.
    if (!detectedZoneLabel.value && manualPlaceId.value) {
      payload.place_id = manualPlaceId.value;
    }
    if (editingId.value) {
      await updateMyAddress(editingId.value, payload);
    } else {
      await createMyAddress(payload);
    }
    addressDialog.value = false;
    await loadAddresses();
  } catch (err) {
    dialogError.value = apiErrorMessage(err) ?? "Échec de l'enregistrement de l'adresse.";
  } finally {
    savingAddress.value = false;
  }
}

function confirmDelete(address: Address) {
  addressToDelete.value = address;
  deleteDialog.value = true;
}

async function performDelete() {
  if (!addressToDelete.value) return;
  deleting.value = true;
  try {
    await deleteMyAddress(addressToDelete.value.id);
    deleteDialog.value = false;
    addressToDelete.value = null;
    await loadAddresses();
  } catch (err) {
    addressesError.value = apiErrorMessage(err) ?? 'Échec de la suppression.';
    deleteDialog.value = false;
  } finally {
    deleting.value = false;
  }
}

onMounted(loadAddresses);
</script>

<style scoped lang="scss">
.address-grid {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.address-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-surface);
}

.address-card__skeleton {
  border-radius: 8px;
}

.address-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.address-card__type {
  font-size: 13px;
  font-weight: 500;
  color: var(--n-ink-2);
}

.address-card__body {
  flex-grow: 1;
  font-style: normal;
  font-size: 14px;
  line-height: 1.55;
}

.address-card__actions {
  display: flex;
  gap: 16px;
}
</style>
