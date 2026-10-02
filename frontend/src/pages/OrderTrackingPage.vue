<template>
  <q-page class="order page-container app-page">
    <router-link
      v-if="!linkToken"
      :to="{ name: 'account', query: { tab: 'orders' } }"
      class="order__back"
    >
      <q-icon name="ph:arrow-left" size="16px" /> {{ $t('tracking.my_orders') }}
    </router-link>

    <div v-if="loading" aria-busy="true" class="order__loading">
      <q-skeleton type="text" width="240px" height="44px" />
      <q-skeleton type="text" width="180px" />
    </div>

    <AppNotice v-else-if="errorMessage" tone="error">
      {{ errorMessage }}
      <template v-if="!linkToken" #action>
        <q-btn
          flat
          :label="$t('tracking.my_orders_btn')"
          :to="{ name: 'account', query: { tab: 'orders' } }"
        />
      </template>
    </AppNotice>

    <template v-else-if="tracking">
      <header class="order__head">
        <h1 class="page-title font-mono order__ref">{{ reference }}</h1>
        <p v-if="order?.created_at" class="order__date">
          {{ $t('tracking.placed_on', { date: formatDate(order.created_at) }) }}
        </p>
        <div class="order__tags">
          <StatusTag
            v-if="order"
            :tone="paymentFacet(order.order_status_name).tone"
            :icon="paymentFacet(order.order_status_name).icon"
            :label="paymentFacet(order.order_status_name).label"
          />
          <StatusTag
            v-if="order && deliveryFacet(order.order_status_name)"
            :tone="deliveryFacet(order.order_status_name)!.tone"
            :icon="deliveryFacet(order.order_status_name)!.icon"
            :label="deliveryFacet(order.order_status_name)!.label"
          />
          <StatusTag
            v-else
            :tone="shippingTone(tracking.overall_status)"
            icon="ph:truck"
            :label="shippingLabel(tracking.overall_status)"
          />
        </div>
      </header>

      <AppNotice
        v-if="linkToken"
        tone="info"
        icon="ph:link"
        class="order__notice"
        data-testid="tracking-link-notice"
      >
        {{ $t('tracking.link_notice') }}
      </AppNotice>

      <AppNotice
        v-for="scenario in tracking.exception_scenarios"
        :key="scenario"
        dense
        tone="warning"
        class="order__notice"
      >
        {{ scenarioLabel(scenario) }}
      </AppNotice>

      <div class="order__layout">
        <div class="order__main">
          <section v-if="departure" class="app-section" data-testid="order-departure">
            <div class="app-panel departure">
              <q-icon name="ph:calendar-check" size="22px" class="departure__icon" />
              <div>
                <p class="departure__title">
                  {{ $t('tracking.departure', { name: departure.name }) }}
                  <StatusTag tone="neutral" :label="statusLabel(departure.status)" />
                </p>
                <p class="departure__text">
                  {{ $t('tracking.cutoff', { date: formatDate(departure.order_cutoff_at) }) }}
                  <template v-if="departure.estimated_delivery_at">
                    {{ $t('tracking.eta', { date: formatDate(departure.estimated_delivery_at) }) }}
                  </template>
                </p>
              </div>
            </div>
          </section>

          <section v-if="lines.length" class="app-section" data-testid="order-lines">
            <div class="app-section__head">
              <h2 class="app-section__title">{{ $t('tracking.items') }}</h2>
            </div>
            <ul class="app-rows">
              <li v-for="line in lines" :key="line.product_id" class="app-row line">
                <component
                  :is="line.product_available ? 'router-link' : 'div'"
                  :to="
                    line.product_available
                      ? { name: 'product-detail', params: { id: line.product_id } }
                      : undefined
                  "
                  class="line__media"
                  tabindex="-1"
                  aria-hidden="true"
                >
                  <ProductImage :src="line.image_url" alt="" glyph-size="24px" />
                </component>
                <div class="app-row__main">
                  <span v-if="line.manufacturer" class="line__brand">{{ line.manufacturer }}</span>
                  <router-link
                    v-if="line.product_available"
                    :to="{ name: 'product-detail', params: { id: line.product_id } }"
                    class="app-row__title"
                  >
                    {{ line.product_name }}
                  </router-link>
                  <span v-else class="app-row__title">{{ line.product_name }}</span>
                  <span class="app-row__meta font-mono">
                    {{ line.quantity }} × {{ money(line.unit_price) }}
                  </span>
                  <span v-if="line.serial_numbers.length" class="app-row__meta">
                    {{ $t('tracking.serials') }}
                    <span class="font-mono">{{ line.serial_numbers.join(', ') }}</span>
                  </span>
                  <span v-if="line.warranty_until" class="app-row__meta">
                    {{
                      $t('tracking.warranty_until', {
                        n: line.warranty_months,
                        date: formatDate(line.warranty_until),
                      })
                    }}
                  </span>
                  <span v-else-if="line.warranty_months" class="app-row__meta">
                    {{ $t('tracking.warranty_from', { n: line.warranty_months }) }}
                  </span>
                </div>
                <span class="font-mono line__total">
                  {{ money(String(Number(line.unit_price) * line.quantity)) }}
                </span>
              </li>
            </ul>
          </section>

          <section class="app-section">
            <div class="app-section__head">
              <h2 class="app-section__title">{{ $t('tracking.routing') }}</h2>
              <span v-if="tracking.trackings.length" class="app-section__hint">
                {{ shippingLabel(tracking.overall_status) }}
              </span>
            </div>

            <div v-if="tracking.trackings.length === 0" class="app-empty legs__empty">
              <q-icon name="ph:package" size="32px" class="text-subtle" />
              <p>{{ $t('tracking.no_legs') }}</p>
            </div>

            <ol v-else class="legs">
              <li
                v-for="segment in sortedSegments"
                :key="segment.id"
                class="leg"
                :class="{
                  'leg--current': segment.sequence_order === tracking.current_route_sequence,
                }"
              >
                <span class="leg__dot" aria-hidden="true" />
                <div class="leg__body">
                  <span class="leg__title">{{
                    legLabel(segment) ?? $t('tracking.step_n', { n: segment.sequence_order })
                  }}</span>
                  <span v-if="segment.carrier_name || segment.tracking_ref" class="leg__meta">
                    {{ segment.carrier_name }}
                    <span v-if="segment.tracking_ref" class="font-mono">
                      {{ segment.carrier_name ? '·' : '' }} {{ segment.tracking_ref }}
                    </span>
                    <a
                      v-if="segment.tracking_url"
                      :href="segment.tracking_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      class="text-link leg__link"
                    >
                      {{ $t('tracking.track_parcel') }}
                      <q-icon name="ph:arrow-square-out" size="14px" />
                    </a>
                  </span>
                  <span v-if="segment.estimated_delivery" class="leg__meta">
                    {{ $t('tracking.leg_eta', { date: formatDate(segment.estimated_delivery) }) }}
                  </span>
                  <span v-if="segment.consolidation_id" class="leg__meta">
                    {{ $t('tracking.consolidated') }}
                  </span>
                  <span v-if="customerNote(segment.notes)" class="leg__meta">
                    {{ customerNote(segment.notes) }}
                  </span>
                  <span v-if="segment.last_status_update" class="leg__time">
                    {{
                      $t('tracking.updated', { date: formatDateTime(segment.last_status_update) })
                    }}
                  </span>
                </div>
              </li>
            </ol>

            <ul v-if="tracking.consolidations.length" class="app-rows consolidations">
              <li v-for="c in tracking.consolidations" :key="c.id" class="app-row">
                <q-icon name="ph:stack" size="20px" class="text-subtle" />
                <div class="app-row__main">
                  <span class="app-row__title">{{ c.name }}</span>
                  <span class="app-row__meta font-mono">{{ c.consolidation_code }}</span>
                </div>
              </li>
            </ul>
          </section>
        </div>

        <aside v-if="order" class="order__aside" :aria-label="$t('tracking.summary')">
          <div class="app-panel summary">
            <h2 class="summary__title">{{ $t('tracking.summary_title') }}</h2>
            <div class="app-kv">
              <span>{{ $t('tracking.subtotal') }}</span>
              <span class="font-mono">{{ money(order.subtotal_amount) }}</span>
            </div>
            <div class="app-kv">
              <span>{{ deliveryLabel ?? $t('tracking.delivery') }}</span>
              <span class="font-mono">{{ money(order.shipping_fee_amount) }}</span>
            </div>
            <div v-if="isPositiveAmount(order.payment_fee_amount)" class="app-kv">
              <span>{{ $t('tracking.payment_fee') }}</span>
              <span class="font-mono">{{ money(order.payment_fee_amount) }}</span>
            </div>
            <div
              v-if="order.discount_code && isPositiveAmount(order.discount_amount)"
              class="app-kv app-kv--credit"
            >
              <span>{{ $t('tracking.discount', { code: order.discount_code }) }}</span>
              <span class="font-mono">−{{ money(order.discount_amount ?? '0') }}</span>
            </div>
            <div class="app-kv app-kv--total">
              <span>{{ $t('tracking.total') }}</span>
              <span class="font-mono">{{ money(order.total_amount) }}</span>
            </div>

            <div v-if="partialPayment" class="summary__block" data-testid="order-partial">
              <div class="app-kv app-kv--credit">
                <span>{{ $t('tracking.paid') }}</span>
                <span class="font-mono">{{ money(partialPayment.paid) }}</span>
              </div>
              <div class="app-kv">
                <span>{{ $t('tracking.due') }}</span>
                <span class="font-mono">{{ money(partialPayment.due) }}</span>
              </div>
              <p class="summary__note">
                {{ $t('tracking.partial_note') }}
              </p>
            </div>

            <div
              v-if="order.payment_plan === 'deposit'"
              class="summary__block"
              data-testid="order-deposit"
            >
              <div class="app-kv">
                <span>{{ $t('tracking.deposit_paid') }}</span>
                <span class="font-mono">{{ money(order.deposit_amount) }}</span>
              </div>
              <div class="app-kv">
                <span>
                  {{ $t('tracking.balance') }}
                  <StatusTag
                    v-if="order.balance_paid_at"
                    tone="ok"
                    :label="$t('tracking.balance_paid')"
                  />
                  <StatusTag
                    v-else-if="order.balance_due"
                    tone="warn"
                    :label="$t('tracking.balance_due_tag')"
                  />
                </span>
                <span class="font-mono">{{ money(order.balance_amount) }}</span>
              </div>
              <template v-if="!order.balance_paid_at">
                <p class="summary__note">
                  {{
                    order.balance_due
                      ? $t('tracking.balance_due_text')
                      : $t('tracking.balance_later_text')
                  }}
                </p>
                <q-btn
                  v-if="balancePayable && !linkToken"
                  unelevated
                  color="primary"
                  :label="$t('tracking.pay_balance', { amount: money(order.balance_amount) })"
                  class="summary__cta"
                  :to="{ name: 'order-balance', params: { id: order.id } }"
                  data-testid="order-pay-balance"
                />
                <p v-else-if="balancePayable" class="summary__note">
                  {{ $t('tracking.balance_login') }}
                </p>
              </template>
            </div>

            <dl class="summary__facts">
              <template v-if="paymentMethod">
                <dt>{{ $t('tracking.payment') }}</dt>
                <dd>{{ paymentMethod }}</dd>
              </template>
              <template v-if="order.shipping_address">
                <dt>
                  {{
                    order.delivery_type === 'pickup'
                      ? $t('tracking.pickup')
                      : $t('tracking.delivery')
                  }}
                </dt>
                <dd>{{ order.shipping_address }}</dd>
              </template>
            </dl>

            <q-btn
              v-if="invoice"
              outline
              color="primary"
              icon="ph:file-pdf"
              :label="$t('tracking.invoice', { number: invoice.invoice_number })"
              class="summary__cta"
              :loading="downloadingInvoice"
              data-testid="order-invoice"
              @click="onDownloadInvoice"
            />
            <p v-if="invoiceError" class="summary__error">{{ invoiceError }}</p>
          </div>
        </aside>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useDepartureLabels } from '@/composables/useDepartureLabels';
import { computed, onMounted, ref, watch } from 'vue';
import { useMeta } from 'quasar';
import { NOINDEX } from '@/utils/seo';
import { useRoute, useRouter } from 'vue-router';
import { formatDate, formatDateTime, orderRef } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import ProductImage from '@/components/ProductImage.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { getDeparture, type Departure } from '@/api/departures';
import { downloadInvoicePdf, listMyInvoices, type Invoice } from '@/api/invoices';
import {
  getMyOrder,
  getMyOrderLines,
  getMyOrderTracking,
  trackOrderByLink,
  type Order,
  type OrderDetail,
  type OrderLine,
  type OrderTracking,
  type OrderTrackingSegment,
} from '@/api/orders';
import { useAuthStore } from '@/stores/auth';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';
import { isPositiveAmount, orderMoney } from '@/utils/money';
import {
  DELIVERY_TYPES,
  deliveryFacet as deliveryFacetIn,
  paymentFacet as paymentFacetIn,
} from '@/utils/orderStatus';
import { useTranslate } from '@/composables/useTranslate';
import type { StatusTone } from '@app/ui/statusTone';

const { t } = useI18n();
const { statusLabel } = useDepartureLabels();

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();

const orderId = computed(() => String(route.params.id ?? ''));
// Lien signé des e-mails (`/suivi/:id?t=…`) : lecture seule, sans compte.
const linkToken = computed(() => {
  const raw = route.query.t;
  const t = Array.isArray(raw) ? raw[0] : raw;
  return typeof t === 'string' && t.length > 0 ? t : null;
});

const loading = ref(true);
const errorMessage = ref<string | null>(null);
const tracking = ref<OrderTracking | null>(null);
const order = ref<Order | OrderDetail | null>(null);
const departure = ref<Departure | null>(null);
const lines = ref<OrderLine[]>([]);
const invoice = ref<Invoice | null>(null);
const invoiceError = ref<string | null>(null);
const downloadingInvoice = ref(false);

const reference = computed(() => orderRef(order.value?.order_number, orderId.value));
useMeta(() => ({ title: t('tracking.meta_title', { ref: reference.value }), meta: NOINDEX }));

const paymentMethod = computed(() =>
  order.value && 'payment_method_name' in order.value ? order.value.payment_method_name : null,
);

// Paiement en plusieurs fois (espèces au bureau, chèques) : déjà réglé / reste.
const partialPayment = computed(() => {
  const current = order.value;
  if (!current || !('amount_paid' in current) || current.order_status_name !== 'PartiallyPaid')
    return null;
  const paid = current.amount_paid ?? '0';
  const due = current.amount_due ?? '0';
  return Number(due) > 0 ? { paid, due } : null;
});

const tr = useTranslate();
const paymentFacet = (name: string | null | undefined) => paymentFacetIn(name, tr);
const deliveryFacet = (name: string | null | undefined) => deliveryFacetIn(name, tr);

const deliveryLabel = computed(() => {
  const type = order.value?.delivery_type;
  if (!type) return null;
  return DELIVERY_TYPES.includes(type) ? t(`order_status.delivery_type.${type}`) : type;
});

function money(raw: string): string {
  return orderMoney(raw, order.value?.currency, currencyStore.reference);
}

// Le solde peut se régler dès que l'acompte est encaissé, pas seulement
// quand il est demandé.
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

const sortedSegments = computed(() =>
  [...(tracking.value?.trackings ?? [])].sort((a, b) => a.sequence_order - b.sequence_order),
);

const SHIPPING_LABELS = new Set([
  'unknown',
  'pending',
  'preparing',
  'ready',
  'shipped',
  'in_transit',
  'customs',
  'out_for_delivery',
  'delivered',
  'cancelled',
  'returned',
]);

function humanize(code: string): string {
  const text = code.replace(/[_-]+/g, ' ').trim().toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function shippingLabel(code: string): string {
  return SHIPPING_LABELS.has(code) ? t(`tracking.ship.${code}`) : humanize(code);
}

function shippingTone(code: string): StatusTone {
  if (code === 'delivered') return 'ok';
  if (code === 'cancelled' || code === 'returned' || code.endsWith('_failed')) return 'danger';
  return 'neutral';
}

const MODE_LABELS = new Set(['air', 'sea', 'road', 'pickup']);

/** « France → Papeete (avion) », sinon le libellé de la route. */
function legLabel(segment: OrderTrackingSegment): string | null {
  const from = segment.from_place_name;
  const to = segment.to_place_name;
  if (!from || !to) return segment.route_label;
  const mode = segment.mode
    ? MODE_LABELS.has(segment.mode)
      ? t(`tracking.mode.${segment.mode}`)
      : segment.mode
    : null;
  return mode ? `${from} → ${to} (${mode})` : `${from} → ${to}`;
}

/** Seules les vraies notes transporteur s'affichent, pas les métadonnées
 * internes historiquement rangées au même endroit (« origin=…; sequence=1 »). */
function customerNote(note: string | null): string | null {
  if (!note) return null;
  if (/\b(origin|segment|sequence|quantity)=/.test(note)) return null;
  return note;
}

const SCENARIO_LABELS = new Set(['supplier_delay', 'parcel_split', 'segment_failure']);

function scenarioLabel(code: string): string {
  return SCENARIO_LABELS.has(code) ? t(`tracking.scenario.${code}`) : humanize(code);
}

const NOT_FOUND = {
  get notFound() {
    return t('tracking.not_found');
  },
  get forbidden() {
    return t('tracking.forbidden');
  },
};

async function onDownloadInvoice() {
  if (!invoice.value) return;
  downloadingInvoice.value = true;
  invoiceError.value = null;
  try {
    await downloadInvoicePdf(invoice.value);
  } catch (err) {
    invoiceError.value = apiErrorMessage(err) ?? t('tracking.invoice_failed');
  } finally {
    downloadingInvoice.value = false;
  }
}

async function loadDeparture(id: string | null | undefined) {
  departure.value = id ? await getDeparture(id).catch(() => null) : null;
}

async function loadFromLink(token: string) {
  try {
    const tracked = await trackOrderByLink(orderId.value, token);
    tracking.value = tracked.tracking;
    order.value = tracked.order;
    lines.value = tracked.lines;
    await loadDeparture(tracked.order.grouped_departure_id);
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, NOT_FOUND) ?? t('tracking.link_invalid');
  }
}

async function loadMine() {
  // Le suivi porte la page ; la commande, les lignes et la facture sont
  // chargées au mieux et ne la bloquent pas.
  const [trackingResult, orderResult, linesResult, invoicesResult] = await Promise.allSettled([
    getMyOrderTracking(orderId.value),
    getMyOrder(orderId.value),
    getMyOrderLines(orderId.value),
    listMyInvoices(),
  ]);
  if (trackingResult.status === 'rejected') {
    errorMessage.value =
      apiErrorMessage(trackingResult.reason, NOT_FOUND) ?? t('tracking.load_failed');
    return;
  }
  tracking.value = trackingResult.value;
  lines.value = linesResult.status === 'fulfilled' ? linesResult.value : [];
  if (invoicesResult.status === 'fulfilled') {
    invoice.value = invoicesResult.value.find((i) => i.order_id === orderId.value) ?? null;
  }
  if (orderResult.status === 'fulfilled') {
    order.value = orderResult.value;
    await loadDeparture(orderResult.value.grouped_departure_id);
  }
}

async function load() {
  const token = linkToken.value;
  if (!token && !authStore.isAuthenticated) {
    await router.replace({
      name: 'login',
      query: { redirect: `/mon-compte/commandes/${orderId.value}` },
    });
    return;
  }
  loading.value = true;
  errorMessage.value = null;
  tracking.value = null;
  order.value = null;
  lines.value = [];
  invoice.value = null;
  departure.value = null;
  if (token) await loadFromLink(token);
  else await loadMine();
  loading.value = false;
}

onMounted(load);
// Le routeur réutilise le composant d'une commande à l'autre.
watch(orderId, (next, previous) => {
  if (next && next !== previous) void load();
});
</script>

<style scoped lang="scss">
.order__back {
  margin-bottom: 20px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.order__loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.order__head {
  margin-bottom: 32px;
}

.order__ref {
  font-weight: 600;
  letter-spacing: -0.02em;
}

.order__date {
  margin: 8px 0 0;
  color: var(--n-ink-2);
}

.order__tags {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;

  .status-tag + .status-tag {
    margin-left: 0;
  }
}

.order__notice {
  margin-bottom: 16px;
}

.order__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 64px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 40px;
  }
}

.order__aside {
  position: sticky;
  top: 88px;

  @media (max-width: 1023px) {
    position: static;
    order: -1;
  }
}

.departure {
  display: flex;
  gap: 14px;
}

.departure__icon {
  flex-shrink: 0;
  color: var(--n-ink-2);
}

.departure__title {
  margin: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-weight: 500;
}

.departure__text {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--n-ink-2);
}

.line {
  align-items: flex-start;
}

.line__media {
  flex-shrink: 0;
  width: 72px;
  display: block;
}

.line__brand {
  font-size: 13px;
  color: var(--n-ink-2);
}

.line__total {
  flex-shrink: 0;
  font-weight: 600;
  white-space: nowrap;

  @media (max-width: 599px) {
    margin-left: 86px;
  }
}

.legs {
  margin: 0;
  padding: 0;
  list-style: none;
}

.legs__empty p {
  margin: 0;
}

.leg {
  position: relative;
  padding: 0 0 28px 28px;

  &::before {
    content: '';
    position: absolute;
    left: 5px;
    top: 16px;
    bottom: 0;
    width: 1px;
    background: var(--n-line-2);
  }

  &:last-child {
    padding-bottom: 0;

    &::before {
      display: none;
    }
  }
}

.leg__dot {
  position: absolute;
  left: 0;
  top: 5px;
  width: 11px;
  height: 11px;
  border: 2px solid var(--n-ink-3);
  border-radius: 999px;
  background: var(--n-bg);

  .leg--current & {
    border-color: var(--n-accent);
    background: var(--n-accent);
  }
}

.leg__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.leg__title {
  font-weight: 500;
}

.leg__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ink-2);
}

.leg__link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.leg__time {
  font-size: 12px;
  color: var(--n-ink-3);
}

.consolidations {
  margin-top: 24px;
}

.summary__title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.summary__block {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--n-line-2);
}

.summary__note {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--n-ink-2);
}

.summary__cta {
  width: 100%;
  min-height: 44px;
  margin-top: 16px;
}

.summary__facts {
  margin: 20px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--n-line-2);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 16px;
  font-size: 14px;

  dt {
    color: var(--n-ink-3);
  }

  dd {
    margin: 0;
  }
}

.summary__error {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--n-danger);
}
</style>
