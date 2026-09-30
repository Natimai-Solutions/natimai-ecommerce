<template>
  <q-page class="order-tracking-page page-container app-page">
    <div class="row items-center q-mb-md">
      <div class="col">
        <h1 class="page-title">Suivi de commande</h1>
        <div class="text-caption text-grey-7">Commande #{{ shortId }}</div>
      </div>
      <q-btn
        v-if="!linkToken"
        flat
        color="primary"
        icon="arrow_back"
        label="Mes commandes"
        no-caps
        :to="{ name: 'account', query: { tab: 'orders' } }"
      />
    </div>

    <AppNotice
      v-if="linkToken && !loading"
      tone="info"
      icon="ph:link"
      class="q-mb-md"
      data-testid="tracking-link-notice"
    >
      Vous suivez cette commande depuis le lien reçu par e-mail. Gardez-le : il permet à quiconque
      le détient de consulter l'avancement de cette commande.
    </AppNotice>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner color="primary" size="2.5em" />
    </div>

    <AppNotice v-else-if="errorMessage" tone="error">
      {{ errorMessage }}
      <template v-if="!linkToken" #action>
        <q-btn flat label="Mes commandes" :to="{ name: 'account', query: { tab: 'orders' } }" />
      </template>
    </AppNotice>

    <template v-else-if="tracking">
      <!-- Overall status -->
      <q-card flat bordered class="q-mb-md">
        <q-card-section class="row items-center">
          <div class="col">
            <div class="text-caption text-grey-7">Statut d'expédition</div>
            <div class="text-h6">{{ statusLabel(tracking.overall_status) }}</div>
          </div>
          <StatusTag
            :tone="toneOf(statusColor(tracking.overall_status))"
            :icon="statusIcon(tracking.overall_status)"
            :label="statusLabel(tracking.overall_status)"
          />
        </q-card-section>
      </q-card>

      <!-- Cost recap (subtotal / last-leg delivery / total) -->
      <q-card v-if="departure" flat bordered class="q-mb-md" data-testid="order-departure">
        <q-card-section>
          <div class="row items-center q-gutter-sm">
            <div class="col text-subtitle1 text-weight-medium">
              <q-icon name="ph:calendar-check" class="q-mr-xs" />
              Départ groupé « {{ departure.name }} »
            </div>
            <StatusTag tone="neutral" :label="departureStatusLabel(departure.status)" />
          </div>
          <div class="text-body2 q-mt-xs">
            Clôture des commandes le {{ formatDate(departure.order_cutoff_at) }}
            <template v-if="departure.estimated_delivery_at">
              · Livraison estimée le {{ formatDate(departure.estimated_delivery_at) }}
            </template>
          </div>
        </q-card-section>
      </q-card>

      <!-- Deposit order: what was paid, what is left, pay the balance -->
      <q-card
        v-if="order && order.payment_plan === 'deposit'"
        flat
        bordered
        class="q-mb-md"
        data-testid="order-deposit"
      >
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium q-mb-sm">
            <q-icon name="ph:piggy-bank" class="q-mr-xs" />Commande avec acompte
          </div>
          <div class="row justify-between q-mb-xs">
            <span>Acompte versé</span><span>{{ money(order.deposit_amount) }}</span>
          </div>
          <div class="row justify-between q-mb-xs">
            <span>Solde</span>
            <span class="row items-center q-gutter-x-sm">
              <StatusTag v-if="order.balance_paid_at" tone="ok" label="Réglé" />
              <StatusTag v-else-if="order.balance_due" tone="warn" label="À régler" />
              <span>{{ money(order.balance_amount) }}</span>
            </span>
          </div>
          <template v-if="!order.balance_paid_at">
            <div v-if="order.balance_due" class="text-body2 q-mt-sm">
              Vos articles sont arrivés : réglez le solde pour les récupérer.
            </div>
            <div v-else class="text-caption text-grey-8 q-mt-sm">
              Le solde vous sera demandé à la réception de vos articles ; vous pouvez aussi le
              régler dès maintenant.
            </div>
            <q-btn
              v-if="balancePayable && !linkToken"
              color="primary"
              icon="payments"
              :label="`Régler le solde (${money(order.balance_amount)})`"
              class="q-mt-sm"
              no-caps
              :to="{ name: 'order-balance', params: { id: order.id } }"
              data-testid="order-pay-balance"
            />
            <div v-else-if="balancePayable" class="text-caption text-grey-8 q-mt-sm">
              Pour régler le solde, connectez-vous à votre espace client.
            </div>
          </template>
        </q-card-section>
      </q-card>

      <!-- Products, serial numbers and warranty -->
      <q-card v-if="lines.length" flat bordered class="q-mb-md" data-testid="order-lines">
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium q-mb-sm">Articles</div>
          <q-list dense separator>
            <q-item v-for="line in lines" :key="line.product_id" class="q-px-none">
              <q-item-section>
                <q-item-label>{{ line.quantity }} × {{ line.product_name }}</q-item-label>
                <q-item-label v-if="line.serial_numbers.length" caption>
                  N° de série : {{ line.serial_numbers.join(', ') }}
                </q-item-label>
                <q-item-label v-if="line.warranty_until" caption>
                  Garantie {{ line.warranty_months }} mois, jusqu'au
                  {{ formatDate(line.warranty_until) }}
                </q-item-label>
                <q-item-label v-else-if="line.warranty_months" caption>
                  Garantie {{ line.warranty_months }} mois à compter de la remise
                </q-item-label>
              </q-item-section>
              <q-item-section side>{{ money(line.unit_price) }}</q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>

      <q-card v-if="order" flat bordered class="q-mb-md">
        <q-card-section>
          <div class="text-subtitle1 text-weight-medium q-mb-sm">Récapitulatif</div>
          <div class="row justify-between q-mb-xs">
            <span>Sous-total</span>
            <span>{{ money(order.subtotal_amount) }}</span>
          </div>
          <div class="row justify-between q-mb-xs">
            <span>
              <q-icon name="local_shipping" size="xs" class="q-mr-xs" />
              Livraison<template v-if="deliveryLabel"> : {{ deliveryLabel }}</template>
            </span>
            <span>{{ money(order.shipping_fee_amount) }}</span>
          </div>
          <div v-if="hasFee(order.payment_fee_amount)" class="row justify-between q-mb-xs">
            <span>Frais de paiement</span>
            <span>{{ money(order.payment_fee_amount) }}</span>
          </div>
          <div
            v-if="order.discount_code && hasFee(order.discount_amount ?? '0')"
            class="row justify-between q-mb-xs text-positive"
          >
            <span>Remise {{ order.discount_code }}</span>
            <span>-{{ money(order.discount_amount ?? '0') }}</span>
          </div>
          <q-separator class="q-my-sm" />
          <div class="row justify-between text-weight-bold">
            <span>Total</span>
            <span>{{ money(order.total_amount) }}</span>
          </div>
        </q-card-section>
      </q-card>

      <!-- Exception scenarios -->
      <AppNotice
        v-for="scenario in tracking.exception_scenarios"
        :key="scenario"
        dense
        tone="warning"
        class="q-mb-sm"
      >
        {{ scenarioLabel(scenario) }}
      </AppNotice>

      <!-- No tracking yet -->
      <AppNotice v-if="tracking.trackings.length === 0" tone="info" class="q-mt-md">
        Aucune information d'expédition n'est encore disponible pour cette commande.
      </AppNotice>

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
                <div v-if="legLabel(segment)" class="text-weight-medium text-grey-9">
                  <q-icon name="route" size="xs" class="q-mr-xs" />
                  {{ legLabel(segment) }}
                </div>
                <div v-if="segment.tracking_ref || segment.carrier_name" class="row items-center">
                  <q-icon name="local_shipping" size="xs" class="q-mr-xs" />
                  <span v-if="segment.carrier_name">{{ segment.carrier_name }}</span>
                  <span v-if="segment.carrier_name && segment.tracking_ref" class="q-mx-xs">·</span>
                  <span v-if="segment.tracking_ref" class="text-weight-medium">{{
                    segment.tracking_ref
                  }}</span>
                  <q-btn
                    v-if="segment.tracking_url"
                    flat
                    dense
                    no-caps
                    size="sm"
                    color="primary"
                    icon-right="open_in_new"
                    label="Suivre le colis"
                    type="a"
                    :href="segment.tracking_url"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="q-ml-sm"
                  />
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
import StatusTag from '@/components/StatusTag.vue';
import { toneOf } from '@/utils/statusTone';
import AppNotice from '@/components/AppNotice.vue';
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { departureStatusLabel, formatXpf } from '@app/utils';
import { useAuthStore } from '@/stores/auth';
import {
  getMyOrder,
  getMyOrderLines,
  getMyOrderTracking,
  trackOrderByLink,
  type Order,
  type OrderLine,
  type OrderTracking,
  type OrderTrackingSegment,
} from '@/api/orders';
import { getDeparture, type Departure } from '@/api/departures';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const orderId = computed(() => String(route.params.id ?? ''));
// Signed link from the e-mails (`/suivi/:id?t=…`): read-only, no account.
const linkToken = computed(() => {
  const raw = route.query.t;
  const t = Array.isArray(raw) ? raw[0] : raw;
  return typeof t === 'string' && t.length > 0 ? t : null;
});
const shortId = computed(() => orderId.value.slice(0, 8));

const loading = ref(true);
const errorMessage = ref<string | null>(null);
const tracking = ref<OrderTracking | null>(null);
const order = ref<Order | null>(null);
// Grouped departure the order is attached to (best-effort, like the order).
const departure = ref<Departure | null>(null);
// Products with their serial numbers and warranty end (best-effort too).
const lines = ref<OrderLine[]>([]);

const DELIVERY_LABELS: Record<string, string> = {
  pickup: 'Retrait en magasin',
  home_delivery: 'Livraison à domicile',
  air_freight: 'Fret aérien',
};
const deliveryLabel = computed(() => {
  const dt = order.value?.delivery_type;
  return dt ? (DELIVERY_LABELS[dt] ?? prettify(dt)) : null;
});

function money(raw: string): string {
  const n = Number.parseFloat(raw);
  return Number.isFinite(n) ? formatXpf(n) : raw;
}

// The balance can be settled once the deposit is in (any status past the
// first payment), not only when it has been asked for.
const UNPAID_STATUSES = new Set([
  'Pending',
  'AwaitingPayment',
  'PaymentFailed',
  'Cancelled',
  'Refunded',
]);
const balancePayable = computed(() => {
  const o = order.value;
  return (
    !!o &&
    o.payment_plan === 'deposit' &&
    !o.balance_paid_at &&
    !UNPAID_STATUSES.has(o.order_status_name ?? '')
  );
});
function hasFee(raw: string): boolean {
  return Number.parseFloat(raw) > 0;
}

const sortedSegments = computed(() =>
  [...(tracking.value?.trackings ?? [])].sort((a, b) => a.sequence_order - b.sequence_order),
);

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
};

function prettify(code: string): string {
  return code.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusLabel(code: string): string {
  return STATUS_LABELS[code] ?? prettify(code);
}

function statusColor(code: string): string {
  if (code === 'delivered') return 'green';
  if (code === 'cancelled' || code === 'returned' || code.endsWith('_failed')) return 'negative';
  if (code === 'shipped' || code === 'in_transit' || code === 'out_for_delivery') return 'primary';
  return 'grey-7';
}

function statusIcon(code: string): string {
  if (code === 'delivered') return 'check_circle';
  if (code === 'cancelled' || code === 'returned' || code.endsWith('_failed')) return 'cancel';
  if (code === 'shipped' || code === 'in_transit') return 'local_shipping';
  if (code === 'out_for_delivery') return 'local_shipping';
  if (code === 'customs') return 'gavel';
  return 'schedule';
}

function segmentIcon(segment: OrderTrackingSegment): string {
  if (segment.estimated_delivery) return 'local_shipping';
  return 'place';
}

// Transport mode → customer-facing French label.
const MODE_LABELS: Record<string, string> = {
  air: 'avion',
  sea: 'bateau',
  road: 'route',
  pickup: 'retrait',
};

/** e.g. "France → Papeete (avion)" — falls back to the route label or null. */
function legLabel(segment: OrderTrackingSegment): string | null {
  const from = segment.from_place_name;
  const to = segment.to_place_name;
  if (!from || !to) return segment.route_label;
  const mode = segment.mode ? (MODE_LABELS[segment.mode] ?? segment.mode) : null;
  return mode ? `${from} → ${to} (${mode})` : `${from} → ${to}`;
}

/**
 * Only show genuine carrier notes. The public `notes` field historically also
 * received internal linkage metadata (e.g. "origin=checkout_selected_routes;
 * sequence=1") — those are not meaningful to the customer and are hidden.
 */
function customerNote(note: string | null): string | null {
  if (!note) return null;
  if (/\b(origin|segment|sequence|quantity)=/.test(note)) return null;
  return note;
}

const SCENARIO_LABELS: Record<string, string> = {
  supplier_delay: 'Retard fournisseur signalé sur un tronçon.',
  parcel_split: 'Votre commande a été scindée en plusieurs colis.',
  segment_failure: "Un incident est survenu sur un tronçon d'acheminement.",
};

function scenarioLabel(code: string): string {
  return SCENARIO_LABELS[code] ?? prettify(code);
}

function formatDate(raw: string | null): string | null {
  if (!raw) return null;
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { status?: number; data?: unknown } }).response;
    const data = resp?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
    if (resp?.status === 404) return 'Cette commande est introuvable.';
    if (resp?.status === 403) return "Vous n'avez pas accès à cette commande.";
  }
  return null;
}

async function loadFromLink(token: string) {
  loading.value = true;
  errorMessage.value = null;
  try {
    const tracked = await trackOrderByLink(orderId.value, token);
    tracking.value = tracked.tracking;
    order.value = tracked.order;
    lines.value = tracked.lines;
    const departureId = tracked.order.grouped_departure_id;
    departure.value = departureId ? await getDeparture(departureId).catch(() => null) : null;
  } catch (err) {
    errorMessage.value =
      extractError(err) ?? 'Ce lien de suivi est invalide ou la commande est introuvable.';
  } finally {
    loading.value = false;
  }
}

async function load() {
  loading.value = true;
  errorMessage.value = null;
  try {
    // Tracking drives the page; the order (for the cost recap) is best-effort.
    const [trackingResult, orderResult, linesResult] = await Promise.allSettled([
      getMyOrderTracking(orderId.value),
      getMyOrder(orderId.value),
      getMyOrderLines(orderId.value),
    ]);
    if (trackingResult.status === 'fulfilled') {
      tracking.value = trackingResult.value;
    } else {
      throw trackingResult.reason;
    }
    lines.value = linesResult.status === 'fulfilled' ? linesResult.value : [];
    if (orderResult.status === 'fulfilled') {
      order.value = orderResult.value;
      const departureId = orderResult.value?.grouped_departure_id;
      departure.value = departureId ? await getDeparture(departureId).catch(() => null) : null;
    }
  } catch (err) {
    errorMessage.value = extractError(err) ?? 'Impossible de charger le suivi de cette commande.';
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  const token = linkToken.value;
  if (token) {
    await loadFromLink(token);
    return;
  }
  if (!authStore.isAuthenticated) {
    await router.replace({
      name: 'login',
      query: { redirect: `/mon-compte/commandes/${orderId.value}` },
    });
    return;
  }
  await load();
});
</script>
