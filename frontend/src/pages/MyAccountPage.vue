<template>
  <q-page class="account-page q-pa-md">
    <div class="row items-center q-mb-md">
      <h1 class="text-h5 q-my-none col">Mon compte</h1>
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
              <q-banner v-if="prefsError" class="bg-red-1 text-red-9 q-mb-md" rounded>
                <template #avatar><q-icon name="error_outline" /></template>
                {{ prefsError }}
              </q-banner>
              <q-banner v-if="prefsSaved" class="bg-green-1 text-green-9 q-mb-md" rounded>
                <template #avatar><q-icon name="check_circle" /></template>
                Préférences enregistrées.
              </q-banner>

              <div class="text-subtitle1 text-weight-medium q-mb-sm">Notifications</div>
              <q-toggle
                v-model="prefs.notification_email_enabled"
                label="Recevoir les emails transactionnels (commande, paiement)"
              />
              <q-toggle
                v-model="prefs.notification_shipping_steps"
                label="Recevoir les notifications de suivi d'expédition"
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
                <!-- Devise d'affichage : masquée tant que l'affichage multi-devises
                     (conversion des prix) n'est pas livré — cf. Phase 4. -->
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
            Une adresse doit être validée par notre équipe avant de pouvoir être
            utilisée au paiement.
          </div>
          <q-btn
            color="primary"
            icon="add"
            label="Ajouter"
            no-caps
            @click="openAddressDialog()"
          />
        </div>

        <q-banner v-if="addressesError" class="bg-red-1 text-red-9 q-mb-md" rounded>
          <template #avatar><q-icon name="error_outline" /></template>
          {{ addressesError }}
        </q-banner>

        <div v-if="loadingAddresses" class="text-center q-pa-lg">
          <q-spinner color="primary" size="2em" />
        </div>

        <q-banner
          v-else-if="addresses.length === 0"
          class="bg-blue-1 text-blue-10"
          rounded
        >
          <template #avatar><q-icon name="info" /></template>
          Vous n'avez pas encore enregistré d'adresse.
        </q-banner>

        <div v-else class="row q-col-gutter-md">
          <div
            v-for="address in addresses"
            :key="address.id"
            class="col-12 col-sm-6 col-md-4"
          >
            <q-card flat bordered class="full-height column">
              <q-card-section class="col">
                <div class="row items-center q-mb-xs">
                  <q-chip
                    dense
                    square
                    :color="typeColor(address.type)"
                    text-color="white"
                    :label="typeLabel(address.type)"
                  />
                  <q-space />
                  <q-chip
                    dense
                    square
                    :color="address.is_validated ? 'green' : 'grey-5'"
                    text-color="white"
                    :icon="address.is_validated ? 'verified' : 'schedule'"
                    :label="address.is_validated ? 'Validée' : 'En attente'"
                  />
                </div>
                <div>{{ address.street }}</div>
                <div>{{ address.postal_code }} {{ address.city }}</div>
                <div v-if="address.state">{{ address.state }}</div>
                <div class="text-weight-medium">{{ address.country }}</div>
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
        <q-banner v-if="ordersError" class="bg-red-1 text-red-9 q-mb-md" rounded>
          <template #avatar><q-icon name="error_outline" /></template>
          {{ ordersError }}
        </q-banner>

        <div v-if="loadingOrders" class="text-center q-pa-lg">
          <q-spinner color="primary" size="2em" />
        </div>

        <q-banner
          v-else-if="orders.length === 0"
          class="bg-blue-1 text-blue-10"
          rounded
        >
          <template #avatar><q-icon name="info" /></template>
          Vous n'avez pas encore passé de commande.
        </q-banner>

        <q-list v-else bordered separator class="rounded-borders">
          <q-item v-for="order in orders" :key="order.id">
            <q-item-section avatar>
              <q-icon name="receipt_long" color="primary" />
            </q-item-section>
            <q-item-section>
              <q-item-label>Commande #{{ order.id.slice(0, 8) }}</q-item-label>
              <q-item-label caption>
                {{ formatDate(order.created_at) ?? '—' }}
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
            </q-item-section>
          </q-item>
        </q-list>
      </q-tab-panel>
    </q-tab-panels>

    <!-- ====================== Create / edit address dialog ====================== -->
    <q-dialog v-model="addressDialog">
      <q-card style="min-width: 350px; max-width: 520px">
        <q-card-section class="text-h6">
          {{ editingId ? 'Modifier l\'adresse' : 'Nouvelle adresse' }}
        </q-card-section>
        <q-form @submit.prevent="saveAddress">
          <q-card-section class="q-pt-none">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9 q-mb-md" rounded dense>
              {{ dialogError }}
            </q-banner>
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
            <q-input
              v-model="addressForm.street"
              label="Adresse (rue) *"
              outlined
              dense
              class="q-mb-sm"
              :rules="[(v) => !!v || 'Champ requis']"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="addressForm.postal_code"
                label="Code postal *"
                outlined
                dense
                class="col-5"
                :rules="[(v) => !!v || 'Requis']"
              />
              <q-input
                v-model="addressForm.city"
                label="Ville *"
                outlined
                dense
                class="col-7"
                :rules="[(v) => !!v || 'Requis']"
              />
            </div>
            <q-input
              v-model="addressForm.state"
              label="État / Région"
              outlined
              dense
              class="q-mb-sm q-mt-sm"
            />
            <q-input
              v-model="addressForm.country"
              label="Pays *"
              outlined
              dense
              :rules="[(v) => !!v || 'Champ requis']"
            />
          </q-card-section>
          <q-card-actions align="right" class="q-pa-md q-pt-none">
            <q-btn flat label="Annuler" color="grey-8" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              :label="editingId ? 'Enregistrer' : 'Créer'"
              :loading="savingAddress"
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
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { formatXpf } from '@app/utils'
import { useAuthStore } from 'src/stores/auth'
import {
  getMyPreferences,
  updateMyPreferences,
  type UserPreferences,
} from 'src/api/account'
import {
  createMyAddress,
  deleteMyAddress,
  listMyAddresses,
  updateMyAddress,
  type Address,
  type AddressInput,
  type AddressType,
} from 'src/api/addresses'
import { listMyOrders, type Order } from 'src/api/orders'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

type AccountTab = 'preferences' | 'addresses' | 'orders'
const tab = ref<AccountTab>('preferences')

// --------------------------------------------------------------------------
// Select option sets (labels mirror the backend's allowed enum values).
// --------------------------------------------------------------------------
const shippingModeOptions = [
  { label: 'Rapide (avion)', value: 'rapide' },
  { label: 'Économique (bateau)', value: 'economique' },
  { label: 'Écologique', value: 'ecologique' },
]
const shippingPreferenceOptions = [
  { label: 'Le plus rapide', value: 'fastest' },
  { label: 'Le moins cher', value: 'cheapest' },
  { label: 'Le plus écologique', value: 'eco_friendly' },
]
const localeOptions = [
  { label: 'Français', value: 'fr' },
  { label: 'English', value: 'en' },
]
const addressTypeOptions = [
  { label: 'Livraison', value: 'shipping' },
  { label: 'Facturation', value: 'billing' },
  { label: 'Autre', value: 'other' },
]

// --------------------------------------------------------------------------
// Preferences
// --------------------------------------------------------------------------
const loadingPrefs = ref(true)
const savingPrefs = ref(false)
const prefsError = ref<string | null>(null)
const prefsSaved = ref(false)
const prefs = reactive<Omit<UserPreferences, 'user_id'>>({
  notification_email_enabled: true,
  notification_shipping_steps: true,
  default_shipping_preference: null,
  locale: null,
  currency_pref: null,
  preferred_shipping_mode: null,
})

async function loadPreferences() {
  loadingPrefs.value = true
  prefsError.value = null
  try {
    const data = await getMyPreferences()
    prefs.notification_email_enabled = data.notification_email_enabled
    prefs.notification_shipping_steps = data.notification_shipping_steps
    prefs.default_shipping_preference = data.default_shipping_preference
    prefs.locale = data.locale
    prefs.currency_pref = data.currency_pref
    prefs.preferred_shipping_mode = data.preferred_shipping_mode
  } catch (err) {
    prefsError.value = extractError(err) ?? 'Impossible de charger vos préférences.'
  } finally {
    loadingPrefs.value = false
  }
}

async function savePreferences() {
  savingPrefs.value = true
  prefsError.value = null
  prefsSaved.value = false
  try {
    await updateMyPreferences({ ...prefs })
    prefsSaved.value = true
  } catch (err) {
    prefsError.value = extractError(err) ?? "Échec de l'enregistrement."
  } finally {
    savingPrefs.value = false
  }
}

// --------------------------------------------------------------------------
// Addresses
// --------------------------------------------------------------------------
const loadingAddresses = ref(true)
const addressesError = ref<string | null>(null)
const addresses = ref<Address[]>([])

const addressDialog = ref(false)
const editingId = ref<string | null>(null)
const savingAddress = ref(false)
const dialogError = ref<string | null>(null)
const addressForm = reactive<AddressInput>({
  street: '',
  city: '',
  state: '',
  postal_code: '',
  country: '',
  type: 'shipping',
})

const deleteDialog = ref(false)
const deleting = ref(false)
const addressToDelete = ref<Address | null>(null)

async function loadAddresses() {
  loadingAddresses.value = true
  addressesError.value = null
  try {
    addresses.value = await listMyAddresses()
  } catch (err) {
    addressesError.value = extractError(err) ?? 'Impossible de charger vos adresses.'
  } finally {
    loadingAddresses.value = false
  }
}

function openAddressDialog(address?: Address) {
  dialogError.value = null
  if (address) {
    editingId.value = address.id
    addressForm.street = address.street
    addressForm.city = address.city
    addressForm.state = address.state ?? ''
    addressForm.postal_code = address.postal_code
    addressForm.country = address.country
    addressForm.type = (address.type as AddressType) ?? 'shipping'
  } else {
    editingId.value = null
    addressForm.street = ''
    addressForm.city = ''
    addressForm.state = ''
    addressForm.postal_code = ''
    addressForm.country = ''
    addressForm.type = 'shipping'
  }
  addressDialog.value = true
}

async function saveAddress() {
  savingAddress.value = true
  dialogError.value = null
  try {
    const payload: AddressInput = {
      street: addressForm.street,
      city: addressForm.city,
      state: addressForm.state?.trim() ? addressForm.state : null,
      postal_code: addressForm.postal_code,
      country: addressForm.country,
      type: addressForm.type,
    }
    if (editingId.value) {
      await updateMyAddress(editingId.value, payload)
    } else {
      await createMyAddress(payload)
    }
    addressDialog.value = false
    await loadAddresses()
  } catch (err) {
    dialogError.value = extractError(err) ?? "Échec de l'enregistrement de l'adresse."
  } finally {
    savingAddress.value = false
  }
}

function confirmDelete(address: Address) {
  addressToDelete.value = address
  deleteDialog.value = true
}

async function performDelete() {
  if (!addressToDelete.value) return
  deleting.value = true
  try {
    await deleteMyAddress(addressToDelete.value.id)
    deleteDialog.value = false
    addressToDelete.value = null
    await loadAddresses()
  } catch (err) {
    addressesError.value = extractError(err) ?? 'Échec de la suppression.'
    deleteDialog.value = false
  } finally {
    deleting.value = false
  }
}

// --------------------------------------------------------------------------
// Orders
// --------------------------------------------------------------------------
const loadingOrders = ref(true)
const ordersError = ref<string | null>(null)
const orders = ref<Order[]>([])

async function loadOrders() {
  loadingOrders.value = true
  ordersError.value = null
  try {
    orders.value = await listMyOrders()
  } catch (err) {
    ordersError.value = extractError(err) ?? 'Impossible de charger vos commandes.'
  } finally {
    loadingOrders.value = false
  }
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------
function typeLabel(type: string): string {
  return addressTypeOptions.find((o) => o.value === type)?.label ?? type
}
function typeColor(type: string): string {
  if (type === 'billing') return 'deep-purple'
  if (type === 'shipping') return 'primary'
  return 'grey-7'
}

function formatMoney(raw: string): string {
  const n = Number.parseFloat(raw)
  return Number.isFinite(n) ? formatXpf(n) : raw
}

function formatDate(raw: string | null): string | null {
  if (!raw) return null
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return raw
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/** Extract a human message from a backend AppError / Axios error shape. */
function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
    }
  }
  return null
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    await router.replace({ name: 'login', query: { redirect: '/mon-compte' } })
    return
  }
  const requestedTab = route.query.tab
  if (requestedTab === 'addresses' || requestedTab === 'orders') {
    tab.value = requestedTab
  }
  await Promise.all([loadPreferences(), loadAddresses(), loadOrders()])
})
</script>
