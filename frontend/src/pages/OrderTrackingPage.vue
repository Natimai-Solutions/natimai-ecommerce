<template>
  <q-page class="order-tracking-page q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col">
        <h1 class="text-h5 q-my-none">Suivi de commande</h1>
        <div class="text-caption text-grey-7">Commande #{{ shortId }}</div>
      </div>
      <q-btn
        flat
        color="primary"
        icon="arrow_back"
        label="Mes commandes"
        no-caps
        :to="{ name: 'account', query: { tab: 'orders' } }"
      />
    </div>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner color="primary" size="2.5em" />
    </div>

    <q-banner v-else-if="errorMessage" class="bg-red-1 text-red-9" rounded>
      <template #avatar><q-icon name="error_outline" /></template>
      {{ errorMessage }}
      <template #action>
        <q-btn flat label="Mes commandes" :to="{ name: 'account', query: { tab: 'orders' } }" />
      </template>
    </q-banner>

    <template v-else-if="tracking">
      <!-- Overall status -->
      <q-card flat bordered class="q-mb-md">
        <q-card-section class="row items-center">
          <div class="col">
            <div class="text-caption text-grey-7">Statut d'expédition</div>
            <div class="text-h6">{{ statusLabel(tracking.overall_status) }}</div>
          </div>
          <q-chip
            :color="statusColor(tracking.overall_status)"
            text-color="white"
            :icon="statusIcon(tracking.overall_status)"
            :label="statusLabel(tracking.overall_status)"
            class="text-weight-medium"
          />
        </q-card-section>
      </q-card>

      <!-- Exception scenarios -->
      <q-banner
        v-for="scenario in tracking.exception_scenarios"
        :key="scenario"
        class="bg-orange-1 text-orange-10 q-mb-sm"
        rounded
        dense
      >
        <template #avatar><q-icon name="warning_amber" /></template>
        {{ scenarioLabel(scenario) }}
      </q-banner>

      <!-- No tracking yet -->
      <q-banner
        v-if="tracking.trackings.length === 0"
        class="bg-blue-1 text-blue-10 q-mt-md"
        rounded
      >
        <template #avatar><q-icon name="info" /></template>
        Aucune information d'expédition n'est encore disponible pour cette commande.
      </q-banner>

      <!-- Segments timeline -->
      <q-card v-else flat bordered class="q-mt-md">
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium q-mb-md">Étapes d'acheminement</div>
          <q-timeline color="primary">
            <q-timeline-entry
              v-for="segment in sortedSegments"
              :key="segment.id"
              :title="`Tronçon ${segment.sequence_order}`"
              :subtitle="formatDate(segment.last_status_update) ?? undefined"
              :icon="segmentIcon(segment)"
            >
              <div class="column q-gutter-xs">
                <div v-if="segment.tracking_ref">
                  <q-icon name="qr_code" size="xs" class="q-mr-xs" />
                  Référence transporteur : <span class="text-weight-medium">{{ segment.tracking_ref }}</span>
                </div>
                <div v-if="segment.estimated_delivery">
                  <q-icon name="event" size="xs" class="q-mr-xs" />
                  Livraison estimée : {{ formatDate(segment.estimated_delivery) }}
                </div>
                <div v-if="segment.consolidation_id" class="text-grey-7">
                  <q-icon name="inventory_2" size="xs" class="q-mr-xs" />
                  Regroupé dans un envoi consolidé
                </div>
                <div v-if="customerNote(segment.notes)" class="text-grey-8">
                  {{ customerNote(segment.notes) }}
                </div>
              </div>
            </q-timeline-entry>
          </q-timeline>
        </q-card-section>
      </q-card>

      <!-- Consolidations -->
      <q-card v-if="tracking.consolidations.length > 0" flat bordered class="q-mt-md">
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium q-mb-sm">Envois consolidés</div>
          <q-list dense>
            <q-item v-for="c in tracking.consolidations" :key="c.id" class="q-px-none">
              <q-item-section avatar><q-icon name="inventory_2" color="primary" /></q-item-section>
              <q-item-section>
                <q-item-label>{{ c.name }}</q-item-label>
                <q-item-label caption>{{ c.consolidation_code }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from 'src/stores/auth'
import {
  getMyOrderTracking,
  type OrderTracking,
  type OrderTrackingSegment,
} from 'src/api/orders'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const orderId = computed(() => String(route.params.id ?? ''))
const shortId = computed(() => orderId.value.slice(0, 8))

const loading = ref(true)
const errorMessage = ref<string | null>(null)
const tracking = ref<OrderTracking | null>(null)

const sortedSegments = computed(() =>
  [...(tracking.value?.trackings ?? [])].sort((a, b) => a.sequence_order - b.sequence_order),
)

// --------------------------------------------------------------------------
// Status / scenario presentation (best-effort mapping with prettify fallback)
// --------------------------------------------------------------------------
const STATUS_LABELS: Record<string, string> = {
  unknown: 'En préparation',
  pending: 'En attente',
  preparing: 'En préparation',
  ready: 'Prête à expédier',
  shipped: 'Expédiée',
  in_transit: 'En transit',
  customs: 'En dédouanement',
  out_for_delivery: 'En cours de livraison',
  delivered: 'Livrée',
  cancelled: 'Annulée',
  returned: 'Retournée',
}

function prettify(code: string): string {
  return code
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function statusLabel(code: string): string {
  return STATUS_LABELS[code] ?? prettify(code)
}

function statusColor(code: string): string {
  if (code === 'delivered') return 'green'
  if (code === 'cancelled' || code === 'returned' || code.endsWith('_failed')) return 'negative'
  if (code === 'shipped' || code === 'in_transit' || code === 'out_for_delivery') return 'primary'
  return 'grey-7'
}

function statusIcon(code: string): string {
  if (code === 'delivered') return 'check_circle'
  if (code === 'cancelled' || code === 'returned' || code.endsWith('_failed')) return 'cancel'
  if (code === 'shipped' || code === 'in_transit') return 'local_shipping'
  if (code === 'out_for_delivery') return 'local_shipping'
  if (code === 'customs') return 'gavel'
  return 'schedule'
}

function segmentIcon(segment: OrderTrackingSegment): string {
  if (segment.estimated_delivery) return 'local_shipping'
  return 'place'
}

/**
 * Only show genuine carrier notes. The public `notes` field historically also
 * received internal linkage metadata (e.g. "origin=checkout_selected_routes;
 * sequence=1") — those are not meaningful to the customer and are hidden.
 */
function customerNote(note: string | null): string | null {
  if (!note) return null
  if (/\b(origin|segment|sequence|quantity)=/.test(note)) return null
  return note
}

const SCENARIO_LABELS: Record<string, string> = {
  supplier_delay: 'Retard fournisseur signalé sur un tronçon.',
  parcel_split: 'Votre commande a été scindée en plusieurs colis.',
  segment_failure: 'Un incident est survenu sur un tronçon d\'acheminement.',
}

function scenarioLabel(code: string): string {
  return SCENARIO_LABELS[code] ?? prettify(code)
}

function formatDate(raw: string | null): string | null {
  if (!raw) return null
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return raw
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { status?: number; data?: unknown } }).response
    const data = resp?.data
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
    }
    if (resp?.status === 404) return "Cette commande est introuvable."
    if (resp?.status === 403) return "Vous n'avez pas accès à cette commande."
  }
  return null
}

async function load() {
  loading.value = true
  errorMessage.value = null
  try {
    tracking.value = await getMyOrderTracking(orderId.value)
  } catch (err) {
    errorMessage.value = extractError(err) ?? 'Impossible de charger le suivi de cette commande.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    await router.replace({
      name: 'login',
      query: { redirect: `/mon-compte/commandes/${orderId.value}` },
    })
    return
  }
  await load()
})
</script>
