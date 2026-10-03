<template>
  <div>
    <section v-if="storeCredit" class="app-section" data-testid="account-store-credit">
      <div class="app-panel credit">
        <div v-if="hasCredit" class="credit__main">
          <span class="credit__label">{{ $t('orders.credit') }}</span>
          <span class="credit__amount font-mono">{{ money(storeCredit.balance) }}</span>
          <span class="credit__hint">
            {{ $t('orders.credit_hint') }}
          </span>
        </div>
        <form class="credit__redeem" data-testid="account-gift-card" @submit.prevent="redeem">
          <label class="credit__label" for="gift-card-code">{{ $t('orders.gift_card') }}</label>
          <div class="credit__redeem-row">
            <input
              id="gift-card-code"
              v-model="giftCode"
              class="credit__input font-mono"
              type="text"
              autocomplete="off"
              spellcheck="false"
              :placeholder="$t('orders.gift_card_placeholder')"
              :disabled="redeeming"
            />
            <q-btn
              type="submit"
              unelevated
              no-caps
              color="primary"
              :label="$t('orders.gift_card_redeem')"
              :loading="redeeming"
              :disable="giftCode.trim().length < 4"
            />
          </div>
          <span v-if="redeemError" class="credit__error" role="alert">{{ redeemError }}</span>
          <span v-else-if="redeemed" class="credit__hint" role="status">{{ redeemed }}</span>
        </form>
        <button
          v-if="storeCredit.entries.length"
          type="button"
          class="text-link"
          :aria-expanded="showCreditHistory"
          @click="showCreditHistory = !showCreditHistory"
        >
          {{ showCreditHistory ? $t('orders.hide_history') : $t('orders.show_history') }}
        </button>
      </div>
      <ul v-if="showCreditHistory" class="app-rows credit__history">
        <li v-for="entry in storeCredit.entries" :key="entry.id" class="app-row">
          <div class="app-row__main">
            <span class="app-row__title">
              {{ creditKindLabel(entry.kind) }}
            </span>
            <span class="app-row__meta"
              >{{ entry.reason }} · {{ formatDate(entry.created_at) }}</span
            >
          </div>
          <span
            class="font-mono app-row__side"
            :class="Number(entry.amount) < 0 ? 'text-muted' : 'credit__plus'"
          >
            {{ Number(entry.amount) < 0 ? '−' : '+' }}
            {{ money(String(Math.abs(Number(entry.amount)))) }}
          </span>
        </li>
      </ul>
    </section>

    <section
      v-if="loyalty && (loyalty.rules.enabled || loyalty.points > 0)"
      class="app-section"
      data-testid="account-loyalty"
    >
      <div class="app-panel credit">
        <div class="credit__main">
          <span class="credit__label">{{ $t('orders.loyalty') }}</span>
          <span class="credit__amount font-mono">
            {{ $t('orders.loyalty_points', { n: loyalty.points }) }}
          </span>
          <span class="credit__hint">
            {{
              $t('orders.loyalty_hint', {
                value: money(loyalty.credit_value),
                amount: money(loyalty.rules.amount_per_point),
                point: money(loyalty.rules.point_value),
              })
            }}
          </span>
        </div>
        <div class="credit__redeem">
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="$t('orders.loyalty_convert', { amount: money(loyalty.credit_value) })"
            :disable="loyalty.points < loyalty.rules.min_points_to_convert"
            :loading="converting"
            data-testid="account-loyalty-convert"
            @click="convertAll"
          />
          <span v-if="loyalty.points < loyalty.rules.min_points_to_convert" class="credit__hint">
            {{ $t('orders.loyalty_min', { n: loyalty.rules.min_points_to_convert }) }}
          </span>
          <span v-if="loyaltyError" class="credit__error" role="alert">{{ loyaltyError }}</span>
          <span v-else-if="converted" class="credit__hint" role="status">{{ converted }}</span>
        </div>
        <button
          v-if="loyalty.entries?.length"
          type="button"
          class="text-link"
          :aria-expanded="showLoyaltyHistory"
          @click="showLoyaltyHistory = !showLoyaltyHistory"
        >
          {{ showLoyaltyHistory ? $t('orders.hide_history') : $t('orders.show_history') }}
        </button>
      </div>
      <ul v-if="showLoyaltyHistory" class="app-rows credit__history">
        <li v-for="entry in loyalty.entries ?? []" :key="entry.id" class="app-row">
          <div class="app-row__main">
            <span class="app-row__title">{{ loyaltyKindLabel(entry.kind) }}</span>
            <span class="app-row__meta"
              >{{ entry.reason }} · {{ formatDate(entry.created_at) }}</span
            >
          </div>
          <span
            class="font-mono app-row__side"
            :class="entry.points < 0 ? 'text-muted' : 'credit__plus'"
          >
            {{ entry.points < 0 ? '−' : '+' }} {{ Math.abs(entry.points) }}
          </span>
        </li>
      </ul>
    </section>

    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">{{ $t('orders.title') }}</h2>
      </div>

      <AppNotice v-if="error" tone="error" class="q-mb-md">
        {{ error }}
        <template #action><q-btn flat :label="$t('orders.retry')" @click="reload" /></template>
      </AppNotice>
      <AppNotice v-if="documentsError" dense tone="warning" class="q-mb-md">
        {{ documentsError }}
      </AppNotice>

      <ul v-if="loading && !orders.length" class="app-rows" aria-busy="true">
        <li v-for="n in 3" :key="n" class="app-row">
          <div class="app-row__main">
            <q-skeleton type="text" width="30%" />
            <q-skeleton type="text" width="45%" />
          </div>
        </li>
      </ul>

      <div v-else-if="!orders.length && !error" class="app-empty">
        <q-icon name="ph:receipt" size="36px" class="text-subtle" />
        <h3>{{ $t('orders.none_title') }}</h3>
        <p>{{ $t('orders.none_text') }}</p>
        <q-btn
          unelevated
          color="primary"
          :label="$t('orders.see_catalogue')"
          :to="{ name: 'catalogue' }"
        />
      </div>

      <template v-else>
        <ul class="app-rows" data-testid="account-orders">
          <li v-for="order in orders" :key="order.id" class="app-row order-row">
            <div class="app-row__main">
              <router-link
                :to="{ name: 'order-tracking', params: { id: order.id } }"
                class="app-row__title order-row__ref font-mono"
              >
                {{ orderRef(order.order_number, order.id) }}
              </router-link>
              <span class="app-row__meta">{{
                $t('orders.placed_on', { date: formatDate(order.created_at) })
              }}</span>
              <span class="order-row__tags">
                <StatusTag
                  :tone="paymentFacet(order.order_status_name, tr).tone"
                  :icon="paymentFacet(order.order_status_name, tr).icon"
                  :label="paymentFacet(order.order_status_name, tr).label"
                />
                <StatusTag
                  v-if="deliveryFacet(order.order_status_name, tr)"
                  :tone="deliveryFacet(order.order_status_name, tr)!.tone"
                  :icon="deliveryFacet(order.order_status_name, tr)!.icon"
                  :label="deliveryFacet(order.order_status_name, tr)!.label"
                />
                <StatusTag
                  v-if="order.balance_due"
                  tone="warn"
                  icon="ph:coins"
                  :label="
                    $t('orders.balance_due', {
                      amount: money(order.balance_amount, order.currency),
                    })
                  "
                />
              </span>
              <span v-if="documentsOf(order.id).length" class="order-row__docs">
                <button
                  v-for="doc in documentsOf(order.id)"
                  :key="doc.key"
                  type="button"
                  class="text-link"
                  :disabled="downloading === doc.key"
                  @click="doc.download()"
                >
                  <q-icon name="ph:file-pdf" size="14px" /> {{ doc.label }}
                </button>
              </span>
            </div>
            <div class="app-row__side order-row__side">
              <span class="order-row__total font-mono">
                {{ money(order.total_amount, order.currency) }}
              </span>
              <q-btn
                outline
                color="primary"
                :label="$t('orders.detail')"
                :to="{ name: 'order-tracking', params: { id: order.id } }"
                class="order-row__open"
              />
            </div>
          </li>
        </ul>

        <div v-if="hasMore" class="orders__more">
          <q-btn
            outline
            color="primary"
            :label="$t('orders.more')"
            :loading="loading"
            @click="loadMore"
          />
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useTranslate } from '@/composables/useTranslate';
import { computed, onMounted, ref } from 'vue';
import { formatDate, orderRef } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { downloadCreditNotePdf, listMyCreditNotes, type CreditNote } from '@/api/creditNotes';
import { downloadInvoicePdf, listMyInvoices, type Invoice } from '@/api/invoices';
import { listMyOrders, type Order } from '@/api/orders';
import { redeemGiftCard } from '@/api/giftCards';
import { convertLoyaltyPoints, getMyLoyalty, type LoyaltyAccount } from '@/api/loyalty';
import { getMyStoreCredit, type StoreCreditBalance } from '@/api/storeCredit';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';
import { deliveryFacet, paymentFacet } from '@/utils/orderStatus';

const { t } = useI18n();
const tr = useTranslate();

const PAGE_SIZE = 10;

const currencyStore = useCurrencyStore();

const orders = ref<Order[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const hasMore = ref(false);

const invoices = ref<Invoice[]>([]);
const creditNotes = ref<CreditNote[]>([]);
const documentsError = ref<string | null>(null);
const downloading = ref<string | null>(null);

const storeCredit = ref<StoreCreditBalance | null>(null);
const showCreditHistory = ref(false);
const hasCredit = computed(
  () =>
    !!storeCredit.value &&
    (Number(storeCredit.value.balance) > 0 || storeCredit.value.entries.length > 0),
);

// Loyalty points → store credit (R8 / confort).
const loyalty = ref<LoyaltyAccount | null>(null);
const showLoyaltyHistory = ref(false);
const converting = ref(false);
const loyaltyError = ref<string | null>(null);
const converted = ref<string | null>(null);

function loyaltyKindLabel(kind: string): string {
  return ['earn', 'convert', 'revoke', 'adjust'].includes(kind)
    ? t(`orders.loyalty_kind.${kind}`)
    : kind;
}

async function convertAll() {
  if (!loyalty.value || converting.value) return;
  converting.value = true;
  loyaltyError.value = null;
  converted.value = null;
  const points = loyalty.value.points;
  try {
    loyalty.value = await convertLoyaltyPoints(points);
    converted.value = t('orders.loyalty_done', { n: points });
    storeCredit.value = await getMyStoreCredit().catch(() => storeCredit.value);
  } catch (err) {
    loyaltyError.value = apiErrorMessage(err) ?? t('orders.loyalty_failed');
  } finally {
    converting.value = false;
  }
}

// Gift card / voucher code → store credit (R8 / confort).
const giftCode = ref('');
const redeeming = ref(false);
const redeemError = ref<string | null>(null);
const redeemed = ref<string | null>(null);

async function redeem() {
  const code = giftCode.value.trim();
  if (code.length < 4 || redeeming.value) return;
  redeeming.value = true;
  redeemError.value = null;
  redeemed.value = null;
  try {
    const before = Number(storeCredit.value?.balance ?? 0);
    storeCredit.value = await redeemGiftCard(code);
    const added = Number(storeCredit.value.balance) - before;
    redeemed.value = t('orders.gift_card_done', { amount: money(String(added)) });
    giftCode.value = '';
  } catch (err) {
    redeemError.value = apiErrorMessage(err) ?? t('orders.gift_card_failed');
  } finally {
    redeeming.value = false;
  }
}

function creditKindLabel(kind: string): string {
  return ['grant', 'use', 'revoke'].includes(kind) ? t(`orders.kind.${kind}`) : kind;
}

function money(raw: string, currency?: string | null): string {
  return orderMoney(raw, currency, currencyStore.reference);
}

interface OrderDocument {
  key: string;
  label: string;
  download: () => Promise<void>;
}

const documentsByOrder = computed(() => {
  const map = new Map<string, OrderDocument[]>();
  const push = (orderId: string, doc: OrderDocument) => {
    map.set(orderId, [...(map.get(orderId) ?? []), doc]);
  };
  for (const invoice of invoices.value) {
    push(invoice.order_id, {
      key: invoice.id,
      label: t('orders.invoice', { n: invoice.invoice_number }),
      download: () => runDownload(invoice.id, () => downloadInvoicePdf(invoice)),
    });
  }
  for (const note of creditNotes.value) {
    push(note.order_id, {
      key: note.id,
      label: t('orders.credit_note', { n: note.credit_note_number }),
      download: () => runDownload(note.id, () => downloadCreditNotePdf(note)),
    });
  }
  return map;
});

function documentsOf(orderId: string): OrderDocument[] {
  return documentsByOrder.value.get(orderId) ?? [];
}

async function runDownload(key: string, action: () => Promise<void>) {
  downloading.value = key;
  documentsError.value = null;
  try {
    await action();
  } catch (err) {
    documentsError.value = apiErrorMessage(err) ?? t('orders.download_failed');
  } finally {
    downloading.value = null;
  }
}

async function fetchPage(skip: number) {
  loading.value = true;
  error.value = null;
  try {
    // Une ligne de plus que la page : elle dit s'il en reste, sans compteur.
    const page = await listMyOrders({ skip, limit: PAGE_SIZE + 1 });
    hasMore.value = page.length > PAGE_SIZE;
    orders.value = [...orders.value, ...page.slice(0, PAGE_SIZE)];
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('orders.load_failed');
  } finally {
    loading.value = false;
  }
}

function loadMore() {
  void fetchPage(orders.value.length);
}

function reload() {
  orders.value = [];
  void fetchPage(0);
}

async function loadDocuments() {
  // Les documents ne bloquent jamais la liste : une panne se signale à part.
  const [inv, notes, credit, points] = await Promise.allSettled([
    listMyInvoices(),
    listMyCreditNotes(),
    getMyStoreCredit(),
    getMyLoyalty(),
  ]);
  loyalty.value = points.status === 'fulfilled' ? points.value : null;
  invoices.value = inv.status === 'fulfilled' ? inv.value : [];
  creditNotes.value = notes.status === 'fulfilled' ? notes.value : [];
  storeCredit.value = credit.status === 'fulfilled' ? credit.value : null;
  if (inv.status === 'rejected' || notes.status === 'rejected') {
    documentsError.value = t('orders.docs_unavailable');
  }
}

onMounted(() => {
  void fetchPage(0);
  void loadDocuments();
});
</script>

<style scoped lang="scss">
.credit {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.credit__main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.credit__label {
  font-size: 13px;
  color: var(--n-ink-2);
}

.credit__amount {
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.credit__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}

.credit__history {
  margin-top: 12px;
}

.credit__redeem {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1 1 280px;
}

.credit__redeem-row {
  display: flex;
  gap: 8px;
}

.credit__input {
  flex: 1 1 auto;
  min-width: 0;
  padding: 8px 10px;
  border: 1px solid var(--n-line);
  border-radius: 6px;
  background: var(--n-bg);
  color: inherit;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.credit__error {
  font-size: 13px;
  color: var(--n-danger, #b3261e);
}

.credit__plus {
  color: var(--n-ok);
}

.order-row__ref {
  font-size: 15px;
}

.order-row__tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;

  .status-tag + .status-tag {
    margin-left: 0;
  }
}

.order-row__docs {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.order-row__side {
  @media (max-width: 599px) {
    width: 100%;
    justify-content: space-between;
  }
}

.order-row__total {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.order-row__open {
  min-height: 40px;
}

.orders__more {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}
</style>
