<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('gift_cards.title')" :hint="$t('gift_cards.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('gift_cards.new')"
          data-testid="gift-cards-new"
          @click="openIssue"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-input
        v-model="filters.q"
        dense
        outlined
        clearable
        :placeholder="$t('gift_cards.search')"
        class="admin-toolbar__search"
        data-testid="gift-cards-search"
        @keyup.enter="reload"
        @clear="reload"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-select
        v-model="filters.kind"
        dense
        outlined
        clearable
        emit-value
        map-options
        :options="kindOptions"
        :label="$t('gift_cards.kind')"
        class="admin-toolbar__select"
        @update:model-value="reload"
      />
      <q-select
        v-model="filters.state"
        dense
        outlined
        clearable
        emit-value
        map-options
        :options="stateOptions"
        :label="$t('gift_cards.state')"
        class="admin-toolbar__select"
        @update:model-value="reload"
      />
    </div>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>
    <AppNotice v-if="issued.length" tone="success" class="q-mb-md" data-testid="gift-cards-issued">
      <p class="q-mb-sm">{{ $t('gift_cards.issued', { n: issued.length }) }}</p>
      <ul class="gift-cards__codes">
        <li v-for="card in issued" :key="card.id" class="font-mono">
          {{ card.code }} — {{ formatMoney(card.amount, card.currency) }}
        </li>
      </ul>
      <template #action>
        <q-btn flat no-caps icon="ph:copy" :label="$t('gift_cards.copy')" @click="copyIssued" />
      </template>
    </AppNotice>

    <div v-if="loading && rows.length === 0" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <div v-else-if="rows.length === 0" class="app-empty">
      <q-icon name="ph:gift" size="28px" class="text-subtle" />
      <h3>{{ $t('gift_cards.none') }}</h3>
      <p>{{ $t('gift_cards.none_hint') }}</p>
    </div>

    <q-table
      v-else
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
      data-testid="gift-cards-table"
    >
      <template #body-cell-code="props">
        <q-td :props="props">
          <span class="font-mono text-weight-medium">{{ props.row.code }}</span>
          <div class="text-caption text-subtle">
            {{ kindLabel(props.row.kind)
            }}<span v-if="props.row.note"> · {{ props.row.note }}</span>
          </div>
        </q-td>
      </template>
      <template #body-cell-amount="props">
        <q-td :props="props" class="font-mono text-weight-medium">
          {{ formatMoney(props.row.amount, props.row.currency) }}
        </q-td>
      </template>
      <template #body-cell-recipient="props">
        <q-td :props="props">
          <div v-if="props.row.recipient_email">{{ props.row.recipient_email }}</div>
          <router-link
            v-if="props.row.order_id"
            :to="`/orders/${props.row.order_id}`"
            class="admin-link text-caption"
            >{{ $t('gift_cards.bought') }}</router-link
          >
          <span v-if="!props.row.recipient_email && !props.row.order_id" class="text-subtle"
            >—</span
          >
        </q-td>
      </template>
      <template #body-cell-state="props">
        <q-td :props="props">
          <StatusTag
            :tone="toneOfState(props.row.state)"
            :icon="toneIcon(toneOfState(props.row.state))"
            :label="stateLabel(props.row.state)"
          />
          <div v-if="props.row.redeemed_at" class="text-caption text-subtle">
            {{ formatDateTime(props.row.redeemed_at) }}
            <span v-if="props.row.redeemed_by_email"> · {{ props.row.redeemed_by_email }}</span>
          </div>
          <div v-else-if="props.row.expires_at" class="text-caption text-subtle">
            {{ $t('gift_cards.until', { date: formatDateTime(props.row.expires_at) }) }}
          </div>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn
            v-if="props.row.state === 'active' || props.row.state === 'expired'"
            flat
            dense
            round
            icon="ph:prohibit"
            :disable="busyId === props.row.id"
            @click="cancel(props.row)"
          >
            <q-tooltip>{{ $t('gift_cards.cancel') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-else-if="props.row.state === 'cancelled'"
            flat
            dense
            round
            icon="ph:arrow-counter-clockwise"
            :disable="busyId === props.row.id"
            @click="restore(props.row)"
          >
            <q-tooltip>{{ $t('gift_cards.restore') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <div v-if="count > PAGE_SIZE" class="admin-pagination">
      <span class="text-subtle">
        {{
          $t('gift_cards.page_info', {
            from: page * PAGE_SIZE + 1,
            to: Math.min((page + 1) * PAGE_SIZE, count),
            count,
          })
        }}
      </span>
      <q-btn
        flat
        dense
        no-caps
        icon="ph:caret-left"
        :disable="page === 0"
        @click="goTo(page - 1)"
      />
      <q-btn
        flat
        dense
        no-caps
        icon="ph:caret-right"
        :disable="(page + 1) * PAGE_SIZE >= count"
        @click="goTo(page + 1)"
      />
    </div>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('gift_cards.new_title') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-option-group v-model="form.kind" :options="kindOptions" inline dense />
            <p class="text-caption text-subtle q-mb-none">
              {{
                form.kind === 'voucher' ? $t('gift_cards.voucher_hint') : $t('gift_cards.card_hint')
              }}
            </p>
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.amount"
                :label="$t('gift_cards.amount', { currency })"
                type="number"
                step="1"
                min="1"
                outlined
                dense
                class="col-6"
                :rules="req"
                data-testid="gift-card-amount"
              />
              <q-input
                v-if="form.kind === 'gift_card'"
                v-model.number="form.count"
                :label="$t('gift_cards.count')"
                type="number"
                min="1"
                max="100"
                outlined
                dense
                class="col-6"
              />
            </div>
            <q-input
              v-model="form.recipient_email"
              :label="
                form.kind === 'voucher'
                  ? $t('gift_cards.recipient_required')
                  : $t('gift_cards.recipient')
              "
              type="email"
              outlined
              dense
              :rules="form.kind === 'voucher' ? req : []"
              data-testid="gift-card-recipient"
            />
            <q-input
              v-model="form.expires_at"
              :label="$t('gift_cards.expires')"
              :hint="$t('gift_cards.expires_hint')"
              type="date"
              outlined
              dense
              bottom-slots
            />
            <q-input v-model="form.note" :label="$t('gift_cards.note')" outlined dense />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('gift_cards.issue')"
              :loading="saving"
              data-testid="gift-card-submit"
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
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { toneIcon, type StatusTone } from '@app/ui/statusTone';
import { dayBounds, formatDateTime, formatMoney as money } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import {
  GIFT_CARD_KIND_LABELS,
  GIFT_CARD_STATE_LABELS,
  cancelGiftCard,
  issueGiftCards,
  listGiftCards,
  restoreGiftCard,
  type GiftCard,
  type GiftCardKind,
  type GiftCardState,
} from '@/api/giftCards';
import { useShopConfigStore } from '@/stores/shopConfig';

/**
 * Gift cards and vouchers (R8 / confort): prepaid codes the customer turns
 * into store credit. Cards bought in the shop appear here too (« achetée »).
 */
const { t } = useI18n();
const shopConfig = useShopConfigStore();
const currency = computed(() => shopConfig.currency);

const PAGE_SIZE = 50;
const rows = ref<GiftCard[]>([]);
const count = ref(0);
const page = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const busyId = ref<string | null>(null);
const issued = ref<GiftCard[]>([]);
const filters = reactive({
  q: '',
  kind: null as GiftCardKind | null,
  state: null as GiftCardState | null,
});

const KINDS: GiftCardKind[] = ['gift_card', 'voucher'];
const STATES: GiftCardState[] = ['active', 'redeemed', 'expired', 'cancelled'];

function kindLabel(kind: string): string {
  return KINDS.includes(kind as GiftCardKind)
    ? t(GIFT_CARD_KIND_LABELS[kind as GiftCardKind])
    : kind;
}
function stateLabel(state: string): string {
  return STATES.includes(state as GiftCardState)
    ? t(GIFT_CARD_STATE_LABELS[state as GiftCardState])
    : state;
}
function toneOfState(state: string): StatusTone {
  if (state === 'active') return 'ok';
  if (state === 'expired') return 'warn';
  if (state === 'cancelled') return 'danger';
  return 'neutral';
}

const kindOptions = computed(() => KINDS.map((k) => ({ label: kindLabel(k), value: k })));
const stateOptions = computed(() => STATES.map((s) => ({ label: stateLabel(s), value: s })));

const columns = computed<QTableColumn[]>(() => [
  { name: 'code', label: t('gift_cards.col_code'), field: 'code', align: 'left' },
  { name: 'amount', label: t('gift_cards.col_amount'), field: 'amount', align: 'right' },
  {
    name: 'recipient',
    label: t('gift_cards.col_recipient'),
    field: 'recipient_email',
    align: 'left',
  },
  { name: 'state', label: t('gift_cards.col_state'), field: 'state', align: 'left' },
  {
    name: 'created_at',
    label: t('gift_cards.col_created'),
    field: (r: GiftCard) => (r.created_at ? formatDateTime(r.created_at) : '—'),
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

function formatMoney(amount: string | number, cur?: string | null): string {
  const value = Number(amount);
  return Number.isFinite(value) ? money(value, cur || currency.value) : String(amount);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const result = await listGiftCards({
      q: filters.q.trim() || undefined,
      kind: filters.kind,
      state: filters.state,
      skip: page.value * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
    rows.value = result.data;
    count.value = result.count;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function reload() {
  page.value = 0;
  void load();
}

function goTo(next: number) {
  page.value = Math.max(0, next);
  void load();
}

// --- Issue ---
const dialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const req = [(v: string | number | null) => String(v ?? '').trim() !== '' || ' '];
const form = reactive({
  kind: 'gift_card',
  amount: '',
  count: 1,
  recipient_email: '',
  expires_at: '',
  note: '',
});

function openIssue() {
  Object.assign(form, {
    kind: 'gift_card',
    amount: '',
    count: 1,
    recipient_email: '',
    expires_at: '',
    note: '',
  });
  dialogError.value = null;
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    // Valid through the whole day as the shop sees it, not the browser's.
    const expires = form.expires_at ? dayBounds(form.expires_at).end : null;
    issued.value = await issueGiftCards({
      kind: form.kind,
      amount: String(Number(form.amount)),
      count: form.kind === 'voucher' ? 1 : Math.max(1, Math.min(100, Number(form.count) || 1)),
      recipient_email: form.recipient_email.trim() || null,
      expires_at: expires,
      note: form.note.trim() || null,
    });
    dialog.value = false;
    reload();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function copyIssued() {
  const text = issued.value
    .map((c) => `${c.code} — ${formatMoney(c.amount, c.currency)}`)
    .join('\n');
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard unavailable (insecure context): the codes stay on screen.
  }
}

async function cancel(card: GiftCard) {
  busyId.value = card.id;
  error.value = null;
  try {
    const updated = await cancelGiftCard(card.id);
    rows.value = rows.value.map((r) => (r.id === updated.id ? updated : r));
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    busyId.value = null;
  }
}

async function restore(card: GiftCard) {
  busyId.value = card.id;
  error.value = null;
  try {
    const updated = await restoreGiftCard(card.id);
    rows.value = rows.value.map((r) => (r.id === updated.id ? updated : r));
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    busyId.value = null;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.admin-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.admin-toolbar__search {
  flex: 1 1 240px;
}

.admin-toolbar__select {
  flex: 0 1 200px;
}

.admin-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.gift-cards__codes {
  margin: 0;
  padding-left: 18px;
}
</style>
