<template>
  <q-page class="account-page page-container app-page">
    <div class="row items-center q-mb-md">
      <h1 class="page-title col">Mon compte</h1>
    </div>

    <q-tabs
      v-model="tab"
      align="left"
      class="text-primary q-mb-md"
      active-color="primary"
      indicator-color="primary"
      narrow-indicator
    >
      <q-tab name="preferences" icon="tune" label="Préférences" no-caps />
      <q-tab name="addresses" icon="location_on" label="Adresses" no-caps />
      <q-tab name="orders" icon="receipt_long" label="Commandes" no-caps />
      <q-tab name="group" icon="workspace_premium" label="Groupe tarifaire" no-caps />
    </q-tabs>

    <q-tab-panels v-model="tab" animated keep-alive>
      <!-- ============================ Préférences ============================ -->
      <q-tab-panel name="preferences" class="q-px-none">
        <q-card flat bordered>
          <q-card-section>
            <div v-if="loadingPrefs" class="text-center q-pa-lg">
              <q-spinner color="primary" size="2em" />
            </div>

            <template v-else>
              <AppNotice v-if="prefsError" tone="error" class="q-mb-md">
                {{ prefsError }}
              </AppNotice>
              <AppNotice v-if="prefsSaved" tone="success" class="q-mb-md">
                Préférences enregistrées.
              </AppNotice>

              <div class="text-subtitle1 text-weight-medium q-mb-sm">Notifications</div>
              <q-toggle
                v-model="prefs.notification_email_enabled"
                label="Recevoir les emails transactionnels (commande, paiement)"
              />
              <q-toggle
                v-model="prefs.notification_shipping_steps"
                label="Recevoir les notifications de suivi d'expédition"
              />
              <q-toggle
                v-model="prefs.marketing_email_enabled"
                label="Recevoir les rappels commerciaux (panier oublié, offres)"
              />

              <q-separator class="q-my-md" />

              <div class="text-subtitle1 text-weight-medium q-mb-sm">Livraison & affichage</div>
              <div class="row q-col-gutter-md">
                <q-select
                  v-model="prefs.preferred_shipping_mode"
                  :options="shippingModeOptions"
                  label="Niveau de service import préféré"
                  class="col-12 col-sm-6"
                  emit-value
                  map-options
                  clearable
                  outlined
                  dense
                />
                <q-select
                  v-model="prefs.default_shipping_preference"
                  :options="shippingPreferenceOptions"
                  label="Préférence de livraison par défaut"
                  class="col-12 col-sm-6"
                  emit-value
                  map-options
                  clearable
                  outlined
                  dense
                />
                <q-select
                  v-model="prefs.locale"
                  :options="localeOptions"
                  label="Langue de l'interface"
                  class="col-12 col-sm-6"
                  emit-value
                  map-options
                  clearable
                  outlined
                  dense
                />
                <q-select
                  v-if="currencyStore.available.length > 1"
                  :model-value="currencyStore.currency"
                  :options="currencyStore.available"
                  label="Devise d'affichage"
                  hint="Affichage uniquement : le paiement reste en XPF."
                  class="col-12 col-sm-6"
                  outlined
                  dense
                  @update:model-value="onCurrencyPrefChange"
                />
              </div>

              <div class="row justify-end q-mt-md">
                <q-btn
                  color="primary"
                  label="Enregistrer"
                  icon="save"
                  :loading="savingPrefs"
                  :disable="savingPrefs"
                  @click="savePreferences"
                />
              </div>
            </template>
          </q-card-section>
        </q-card>
      </q-tab-panel>

      <!-- ============================= Adresses ============================= -->
      <q-tab-panel name="addresses" class="q-px-none">
        <div class="row items-center q-mb-md">
          <div class="col text-body2 text-grey-8">
            Une adresse doit être validée par notre équipe avant de pouvoir être utilisée au
            paiement.
          </div>
          <q-btn color="primary" icon="add" label="Ajouter" no-caps @click="openAddressDialog()" />
        </div>

        <AppNotice v-if="addressesError" tone="error" class="q-mb-md">
          {{ addressesError }}
        </AppNotice>

        <div v-if="loadingAddresses" class="text-center q-pa-lg">
          <q-spinner color="primary" size="2em" />
        </div>

        <AppNotice v-else-if="addresses.length === 0" tone="info">
          Vous n'avez pas encore enregistré d'adresse.
        </AppNotice>

        <div v-else class="row q-col-gutter-md">
          <div v-for="address in addresses" :key="address.id" class="col-12 col-sm-6 col-md-4">
            <q-card flat bordered class="full-height column">
              <q-card-section class="col">
                <div class="row items-center q-mb-xs">
                  <StatusTag :label="typeLabel(address.type)" />
                  <q-space />
                  <StatusTag
                    :tone="address.is_validated ? 'ok' : 'neutral'"
                    :icon="address.is_validated ? 'verified' : 'schedule'"
                    :label="address.is_validated ? 'Validée' : 'En attente'"
                  />
                </div>
                <div>{{ address.street }}</div>
                <div>{{ address.postal_code }} {{ address.city }}</div>
                <div v-if="address.state">{{ address.state }}</div>
                <div class="text-weight-medium">{{ countryLabel(address.country) }}</div>
              </q-card-section>
              <q-separator />
              <q-card-actions align="right">
                <q-btn flat dense icon="edit" color="primary" @click="openAddressDialog(address)">
                  <q-tooltip>Modifier</q-tooltip>
                </q-btn>
                <q-btn flat dense icon="delete" color="negative" @click="confirmDelete(address)">
                  <q-tooltip>Supprimer</q-tooltip>
                </q-btn>
              </q-card-actions>
            </q-card>
          </div>
        </div>
      </q-tab-panel>

      <!-- ============================= Commandes ============================= -->
      <q-tab-panel name="orders" class="q-px-none">
        <AppNotice v-if="ordersError" tone="error" class="q-mb-md">
          {{ ordersError }}
        </AppNotice>

        <div v-if="loadingOrders" class="text-center q-pa-lg">
          <q-spinner color="primary" size="2em" />
        </div>

        <AppNotice v-else-if="orders.length === 0" tone="info">
          Vous n'avez pas encore passé de commande.
        </AppNotice>

        <template v-else>
          <AppNotice v-if="invoiceError" dense tone="warning" class="q-mb-md">
            {{ invoiceError }}
          </AppNotice>

          <q-list bordered separator class="rounded-borders">
            <q-item v-for="order in orders" :key="order.id">
              <q-item-section avatar>
                <q-icon name="receipt_long" color="primary" />
              </q-item-section>
              <q-item-section>
                <q-item-label>Commande {{ orderRef(order) }}</q-item-label>
                <q-item-label caption>
                  {{ formatDate(order.created_at) ?? '' }}
                </q-item-label>
                <q-item-label class="q-mt-xs">
                  <StatusTag
                    :tone="toneOf(paymentBadge(order.order_status_name).color)"
                    :icon="paymentBadge(order.order_status_name).icon"
                    :label="paymentBadge(order.order_status_name).label"
                  />
                  <StatusTag
                    v-if="deliveryBadge(order.order_status_name)"
                    :tone="toneOf(deliveryBadge(order.order_status_name)?.color)"
                    :icon="deliveryBadge(order.order_status_name)?.icon ?? 'info'"
                    :label="deliveryBadge(order.order_status_name)?.label ?? ''"
                  />
                </q-item-label>
              </q-item-section>
              <q-item-section side class="text-right">
                <q-item-label class="text-weight-medium">
                  {{ formatMoney(order.total_amount) }}
                </q-item-label>
                <q-btn
                  flat
                  dense
                  no-caps
                  color="primary"
                  icon="local_shipping"
                  label="Suivre"
                  :to="{ name: 'order-tracking', params: { id: order.id } }"
                />
                <q-btn
                  v-if="invoiceByOrderId.get(order.id)"
                  flat
                  dense
                  no-caps
                  color="primary"
                  icon="picture_as_pdf"
                  :label="invoiceByOrderId.get(order.id)?.invoice_number"
                  :loading="downloadingInvoiceId === invoiceByOrderId.get(order.id)?.id"
                  @click="onDownloadInvoice(invoiceByOrderId.get(order.id)!)"
                />
                <q-btn
                  v-for="note in creditNotesByOrderId.get(order.id) ?? []"
                  :key="note.id"
                  flat
                  dense
                  no-caps
                  color="primary"
                  icon="picture_as_pdf"
                  :label="`Avoir ${note.credit_note_number}`"
                  :loading="downloadingCreditNoteId === note.id"
                  @click="onDownloadCreditNote(note)"
                >
                  <q-tooltip>
                    {{ formatMoney(note.total_incl_tax) }} crédité(s)
                    {{ note.reason ? `: ${note.reason}` : '' }}
                  </q-tooltip>
                </q-btn>
              </q-item-section>
            </q-item>
          </q-list>
        </template>
      </q-tab-panel>

      <!-- ============================ Groupe tarifaire ============================ -->
      <q-tab-panel name="group" class="q-px-none">
        <q-card flat bordered>
          <q-card-section>
            <div v-if="loadingGroup" class="text-center q-pa-lg">
              <q-spinner color="primary" size="2em" />
            </div>

            <template v-else>
              <AppNotice v-if="groupError" tone="error" class="q-mb-md">
                {{ groupError }}
              </AppNotice>
              <AppNotice v-if="groupSaved" tone="success" class="q-mb-md">
                Votre demande a été envoyée. Elle sera examinée par notre équipe.
              </AppNotice>

              <div class="text-subtitle1 text-weight-medium q-mb-sm">Votre groupe tarifaire</div>
              <StatusTag
                :label="groupOptions?.current_group?.label ?? 'Standard'"
                icon="workspace_premium"
              />

              <q-separator class="q-my-md" />

              <template v-if="groupSelectOptions.length > 0">
                <div class="text-subtitle1 text-weight-medium q-mb-xs">
                  Demander un autre groupe
                </div>
                <div class="text-body2 text-grey-7 q-mb-md">
                  Réservé aux professionnels et revendeurs. Votre demande sera validée par notre
                  équipe.
                </div>
                <q-form @submit.prevent="submitUpgrade">
                  <q-select
                    v-model="upgradeForm.price_group_id"
                    :options="groupSelectOptions"
                    label="Groupe souhaité *"
                    outlined
                    dense
                    emit-value
                    map-options
                    class="q-mb-md"
                  />
                  <q-input
                    v-model="upgradeForm.business_registration_number"
                    label="Numéro TAHITI / RC (ou équivalent) *"
                    outlined
                    dense
                    class="q-mb-md"
                  />
                  <q-input
                    v-model="upgradeForm.attestation_notes"
                    label="Informations complémentaires (optionnel)"
                    type="textarea"
                    autogrow
                    outlined
                    dense
                    class="q-mb-md"
                  />
                  <q-btn
                    type="submit"
                    color="primary"
                    label="Envoyer la demande"
                    unelevated
                    :loading="submittingGroup"
                    :disable="
                      !upgradeForm.price_group_id ||
                      !upgradeForm.business_registration_number.trim()
                    "
                  />
                </q-form>
              </template>
              <div v-else class="text-body2 text-grey-7">
                Aucun autre groupe n'est disponible à la demande pour le moment.
              </div>

              <template v-if="myUpgradeRequests.length > 0">
                <q-separator class="q-my-md" />
                <div class="text-subtitle1 text-weight-medium q-mb-sm">Mes demandes</div>
                <q-list bordered separator>
                  <q-item v-for="req in myUpgradeRequests" :key="req.id">
                    <q-item-section>
                      <q-item-label>{{ upgradeGroupLabel(req.price_group_id) }}</q-item-label>
                      <q-item-label caption>
                        Demandée le {{ formatDate(req.created_at) }}
                        <template v-if="req.admin_comment">. {{ req.admin_comment }}</template>
                      </q-item-label>
                    </q-item-section>
                    <q-item-section side>
                      <StatusTag
                        :tone="toneOf(upgradeStatusColor(req.status))"
                        :label="upgradeStatusLabel(req.status)"
                      />
                    </q-item-section>
                  </q-item>
                </q-list>
              </template>
            </template>
          </q-card-section>
        </q-card>
      </q-tab-panel>
    </q-tab-panels>

    <!-- ====================== Create / edit address dialog ====================== -->
    <q-dialog v-model="addressDialog">
      <q-card style="min-width: 350px; max-width: 520px">
        <q-card-section class="text-h6">
          {{ editingId ? "Modifier l'adresse" : 'Nouvelle adresse' }}
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
            <AppNotice v-if="detectedZoneLabel" dense tone="success" icon="place" class="q-mt-sm">
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
          <q-card-actions align="right" class="q-pa-md q-pt-none">
            <q-btn flat label="Annuler" color="grey-8" v-close-popup />
            <q-btn
              type="submit"
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
      <q-card>
        <q-card-section class="row items-center">
          <q-icon name="warning" color="negative" size="md" class="q-mr-sm" />
          <span>Supprimer cette adresse ?</span>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Annuler" color="grey-8" v-close-popup />
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
  </q-page>
</template>

<script setup lang="ts">
import StatusTag from 'src/components/StatusTag.vue';
import { toneOf } from 'src/utils/statusTone';
import AppNotice from 'src/components/AppNotice.vue';
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { countryLabel, countryOptions, formatXpf, type CountryOption } from '@app/utils';
import { useAuthStore } from 'src/stores/auth';
import { useCurrencyStore } from 'src/stores/currency';
import { getMyPreferences, updateMyPreferences, type UserPreferences } from 'src/api/account';
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
} from 'src/api/addresses';
import { listMyOrders, type Order } from 'src/api/orders';
import { downloadInvoicePdf, listMyInvoices, type Invoice } from 'src/api/invoices';
import { downloadCreditNotePdf, listMyCreditNotes, type CreditNote } from 'src/api/creditNotes';
import {
  getUpgradeOptions,
  listMyUpgradeRequests,
  submitUpgradeRequest,
  type GroupUpgradeRequest,
  type UpgradeGroupOptions,
  type UpgradeRequestStatus,
} from 'src/api/groupUpgrade';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();

function onCurrencyPrefChange(code: string) {
  void currencyStore.setCurrency(code);
}

type AccountTab = 'preferences' | 'addresses' | 'orders' | 'group';
const tab = ref<AccountTab>('preferences');

// --------------------------------------------------------------------------
// Select option sets (labels mirror the backend's allowed enum values).
// --------------------------------------------------------------------------
const shippingModeOptions = [
  { label: 'Rapide (avion)', value: 'rapide' },
  { label: 'Économique (bateau)', value: 'economique' },
  { label: 'Écologique', value: 'ecologique' },
];
const shippingPreferenceOptions = [
  { label: 'Le plus rapide', value: 'fastest' },
  { label: 'Le moins cher', value: 'cheapest' },
  { label: 'Le plus écologique', value: 'eco_friendly' },
];
const localeOptions = [
  { label: 'Français', value: 'fr' },
  { label: 'English', value: 'en' },
];
const addressTypeOptions = [
  { label: 'Livraison', value: 'shipping' },
  { label: 'Facturation', value: 'billing' },
  { label: 'Autre', value: 'other' },
];

// --------------------------------------------------------------------------
// Preferences
// --------------------------------------------------------------------------
const loadingPrefs = ref(true);
const savingPrefs = ref(false);
const prefsError = ref<string | null>(null);
const prefsSaved = ref(false);
const prefs = reactive<Omit<UserPreferences, 'user_id'>>({
  notification_email_enabled: true,
  notification_shipping_steps: true,
  marketing_email_enabled: true,
  default_shipping_preference: null,
  locale: null,
  currency_pref: null,
  preferred_shipping_mode: null,
});

async function loadPreferences() {
  loadingPrefs.value = true;
  prefsError.value = null;
  try {
    const data = await getMyPreferences();
    prefs.notification_email_enabled = data.notification_email_enabled;
    prefs.notification_shipping_steps = data.notification_shipping_steps;
    prefs.marketing_email_enabled = data.marketing_email_enabled ?? true;
    prefs.default_shipping_preference = data.default_shipping_preference;
    prefs.locale = data.locale;
    prefs.currency_pref = data.currency_pref;
    prefs.preferred_shipping_mode = data.preferred_shipping_mode;
  } catch (err) {
    prefsError.value = extractError(err) ?? 'Impossible de charger vos préférences.';
  } finally {
    loadingPrefs.value = false;
  }
}

async function savePreferences() {
  savingPrefs.value = true;
  prefsError.value = null;
  prefsSaved.value = false;
  try {
    // Keep the bulk save consistent with the live display-currency selection
    // (changed via the header or the selector above, which persist immediately).
    prefs.currency_pref = currencyStore.currency;
    await updateMyPreferences({ ...prefs });
    prefsSaved.value = true;
  } catch (err) {
    prefsError.value = extractError(err) ?? "Échec de l'enregistrement.";
  } finally {
    savingPrefs.value = false;
  }
}

// --------------------------------------------------------------------------
// Addresses
// --------------------------------------------------------------------------
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
    addressesError.value = extractError(err) ?? 'Impossible de charger vos adresses.';
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
    dialogError.value = extractError(err) ?? "Échec de l'enregistrement de l'adresse.";
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
    addressesError.value = extractError(err) ?? 'Échec de la suppression.';
    deleteDialog.value = false;
  } finally {
    deleting.value = false;
  }
}

// --------------------------------------------------------------------------
// Orders
// --------------------------------------------------------------------------
const loadingOrders = ref(true);
const ordersError = ref<string | null>(null);
const orders = ref<Order[]>([]);

async function loadOrders() {
  loadingOrders.value = true;
  ordersError.value = null;
  try {
    orders.value = await listMyOrders();
  } catch (err) {
    ordersError.value = extractError(err) ?? 'Impossible de charger vos commandes.';
  } finally {
    loadingOrders.value = false;
  }
}

// --------------------------------------------------------------------------
// Invoices (M3) — one per paid order, downloadable as PDF
// --------------------------------------------------------------------------
const invoices = ref<Invoice[]>([]);
const invoiceError = ref<string | null>(null);
const downloadingInvoiceId = ref<string | null>(null);

/** Invoice issued for an order, if any (invoices only exist once paid). */
const invoiceByOrderId = computed(() => {
  const map = new Map<string, Invoice>();
  for (const invoice of invoices.value) map.set(invoice.order_id, invoice);
  return map;
});

async function loadInvoices() {
  // A failure here must not hide the orders list: the error is reported
  // inline and the page keeps working without the download buttons.
  try {
    invoices.value = await listMyInvoices();
  } catch (err) {
    invoiceError.value = extractError(err) ?? 'Impossible de charger vos factures.';
  }
}

async function onDownloadInvoice(invoice: Invoice) {
  downloadingInvoiceId.value = invoice.id;
  invoiceError.value = null;
  try {
    await downloadInvoicePdf(invoice);
  } catch (err) {
    invoiceError.value = extractError(err) ?? 'Le téléchargement de la facture a échoué.';
  } finally {
    downloadingInvoiceId.value = null;
  }
}

// --------------------------------------------------------------------------
// Credit notes (Z2) — one per refund, correcting the invoice; several per order
// --------------------------------------------------------------------------
const creditNotes = ref<CreditNote[]>([]);
const downloadingCreditNoteId = ref<string | null>(null);

const creditNotesByOrderId = computed(() => {
  const map = new Map<string, CreditNote[]>();
  for (const note of creditNotes.value) {
    const list = map.get(note.order_id) ?? [];
    list.push(note);
    map.set(note.order_id, list);
  }
  return map;
});

async function loadCreditNotes() {
  // Same rule as the invoices: a failure is reported inline, never blocking.
  try {
    creditNotes.value = await listMyCreditNotes();
  } catch (err) {
    invoiceError.value = extractError(err) ?? 'Impossible de charger vos avoirs.';
  }
}

async function onDownloadCreditNote(note: CreditNote) {
  downloadingCreditNoteId.value = note.id;
  invoiceError.value = null;
  try {
    await downloadCreditNotePdf(note);
  } catch (err) {
    invoiceError.value = extractError(err) ?? "Le téléchargement de l'avoir a échoué.";
  } finally {
    downloadingCreditNoteId.value = null;
  }
}

/** Human-readable order reference: CMD-2026-00042, else the legacy short id. */
function orderRef(order: Order): string {
  return order.order_number ?? `#${order.id.slice(0, 8)}`;
}

// --------------------------------------------------------------------------
// Group upgrade
// --------------------------------------------------------------------------
const loadingGroup = ref(true);
const groupError = ref<string | null>(null);
const groupSaved = ref(false);
const submittingGroup = ref(false);
const groupOptions = ref<UpgradeGroupOptions | null>(null);
const myUpgradeRequests = ref<GroupUpgradeRequest[]>([]);
const upgradeForm = reactive({
  price_group_id: null as string | null,
  business_registration_number: '',
  attestation_notes: '',
});

const groupSelectOptions = computed(() =>
  (groupOptions.value?.available_groups ?? []).map((g) => ({ label: g.label, value: g.id })),
);

async function loadGroup() {
  loadingGroup.value = true;
  groupError.value = null;
  try {
    const [options, requests] = await Promise.all([getUpgradeOptions(), listMyUpgradeRequests()]);
    groupOptions.value = options;
    myUpgradeRequests.value = requests;
  } catch (err) {
    groupError.value = extractError(err) ?? 'Impossible de charger votre groupe tarifaire.';
  } finally {
    loadingGroup.value = false;
  }
}

async function submitUpgrade() {
  if (!upgradeForm.price_group_id || !upgradeForm.business_registration_number.trim()) return;
  submittingGroup.value = true;
  groupError.value = null;
  groupSaved.value = false;
  try {
    await submitUpgradeRequest({
      price_group_id: upgradeForm.price_group_id,
      business_registration_number: upgradeForm.business_registration_number.trim(),
      attestation_notes: upgradeForm.attestation_notes.trim() || null,
    });
    groupSaved.value = true;
    upgradeForm.price_group_id = null;
    upgradeForm.business_registration_number = '';
    upgradeForm.attestation_notes = '';
    await loadGroup();
  } catch (err) {
    groupError.value = extractError(err) ?? "Échec de l'envoi de la demande.";
  } finally {
    submittingGroup.value = false;
  }
}

function upgradeGroupLabel(priceGroupId: string): string {
  const all = [
    ...(groupOptions.value?.current_group ? [groupOptions.value.current_group] : []),
    ...(groupOptions.value?.available_groups ?? []),
  ];
  return all.find((g) => g.id === priceGroupId)?.label ?? 'Groupe';
}

const UPGRADE_STATUS_LABELS: Record<UpgradeRequestStatus, string> = {
  PENDING: 'En attente',
  APPROVED: 'Approuvée',
  REJECTED: 'Refusée',
};
function upgradeStatusLabel(s: UpgradeRequestStatus): string {
  return UPGRADE_STATUS_LABELS[s] ?? s;
}
function upgradeStatusColor(s: UpgradeRequestStatus): string {
  if (s === 'APPROVED') return 'green';
  if (s === 'REJECTED') return 'negative';
  return 'orange';
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------
function typeLabel(type: string): string {
  return addressTypeOptions.find((o) => o.value === type)?.label ?? type;
}
function formatMoney(raw: string): string {
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? formatXpf(n) : raw;
}

function formatDate(raw: string | null): string | null {
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// Order status (payment/fulfillment) → customer-facing label & colour.
const ORDER_STATUS_LABELS: Record<string, string> = {
  Pending: 'En attente',
  AwaitingPayment: 'En attente de paiement',
  Paid: 'Payée',
  PaymentFailed: 'Paiement refusé',
  Processing: 'En préparation',
  Shipped: 'Expédiée',
  Delivered: 'Livrée',
  Cancelled: 'Annulée',
};

function orderStatusLabel(name: string | null): string {
  if (!name) return 'En attente';
  return ORDER_STATUS_LABELS[name] ?? name;
}

// The order lifecycle status conflates payment + fulfillment; split it into two
// customer-facing facets (paiement / livraison) derived from the single status.
interface OrderBadge {
  label: string;
  color: string;
  icon: string;
}

const PAYMENT_BADGE: Record<string, OrderBadge> = {
  Pending: { label: 'Paiement en attente', color: 'orange', icon: 'schedule' },
  AwaitingPayment: { label: 'En attente de paiement', color: 'orange', icon: 'schedule' },
  Paid: { label: 'Payée', color: 'green', icon: 'check_circle' },
  PaymentFailed: { label: 'Paiement refusé', color: 'negative', icon: 'cancel' },
  Processing: { label: 'Payée', color: 'green', icon: 'check_circle' },
  Shipped: { label: 'Payée', color: 'green', icon: 'check_circle' },
  Delivered: { label: 'Payée', color: 'green', icon: 'check_circle' },
  Cancelled: { label: 'Annulée', color: 'grey-6', icon: 'block' },
  Refunded: { label: 'Remboursée', color: 'blue', icon: 'undo' },
  PartiallyRefunded: { label: 'Remboursée en partie', color: 'blue', icon: 'undo' },
};

const DELIVERY_BADGE: Record<string, OrderBadge> = {
  Paid: { label: 'En préparation', color: 'grey-7', icon: 'inventory_2' },
  Processing: { label: 'En préparation', color: 'grey-7', icon: 'inventory_2' },
  Shipped: { label: 'Expédiée', color: 'primary', icon: 'local_shipping' },
  Delivered: { label: 'Livrée', color: 'green', icon: 'task_alt' },
};

function paymentBadge(name: string | null): OrderBadge {
  const badge = name ? PAYMENT_BADGE[name] : undefined;
  return badge ?? { label: orderStatusLabel(name), color: 'grey-7', icon: 'info' };
}

function deliveryBadge(name: string | null): OrderBadge | null {
  return (name ? DELIVERY_BADGE[name] : undefined) ?? null;
}

/** Extract a human message from a backend AppError / Axios error shape. */
function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
  }
  return null;
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    await router.replace({ name: 'login', query: { redirect: '/mon-compte' } });
    return;
  }
  const requestedTab = route.query.tab;
  if (requestedTab === 'addresses' || requestedTab === 'orders' || requestedTab === 'group') {
    tab.value = requestedTab;
  }
  await Promise.all([
    loadPreferences(),
    loadAddresses(),
    loadOrders(),
    loadInvoices(),
    loadCreditNotes(),
    loadGroup(),
  ]);
});
</script>
