<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('dashboard.title')" :hint="today">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-lg">
      {{ error }}
      <template #action>
        <q-btn flat dense no-caps :label="$t('common.retry')" @click="load" />
      </template>
    </AppNotice>

    <section
      v-if="checklist && !checklistComplete"
      class="app-section"
      aria-labelledby="setup-title"
      data-testid="dashboard-setup"
    >
      <div class="app-section__head">
        <h2 id="setup-title" class="app-section__title">{{ $t('dashboard.setup') }}</h2>
        <p class="app-section__hint">
          {{ $t('dashboard.setup_progress', { done: checklist.done, total: checklist.total }) }}
        </p>
      </div>
      <ul class="setup-list">
        <li v-for="item in checklist.items" :key="item.key">
          <router-link
            :to="item.to"
            class="setup-item"
            :class="`setup-item--${item.status}`"
            :data-testid="`setup-${item.key}`"
          >
            <q-icon :name="SETUP_ICONS[item.status]" size="18px" class="setup-item__icon" />
            <span class="setup-item__text">
              <span class="setup-item__label">{{ $t(`dashboard.setup_${item.key}`) }}</span>
              <span v-if="item.status !== 'done'" class="setup-item__hint">
                {{ $t(`dashboard.setup_${item.key}_hint`, { n: item.count }) }}
              </span>
            </span>
            <StatusTag
              :label="$t(`dashboard.setup_status_${item.status}`)"
              :tone="SETUP_TONES[item.status]"
            />
          </router-link>
        </li>
      </ul>
    </section>

    <section class="app-section" aria-labelledby="todo-title">
      <div class="app-section__head">
        <h2 id="todo-title" class="app-section__title">{{ $t('dashboard.todo') }}</h2>
        <p v-if="data" class="app-section__hint">
          {{ pendingTotal ? $t('dashboard.pending', pendingTotal) : $t('dashboard.up_to_date') }}
        </p>
      </div>
      <div class="todo-grid" data-testid="dashboard-todo">
        <template v-if="data">
          <router-link
            v-for="item in todoItems"
            :key="item.key"
            :to="item.to"
            class="todo-tile"
            :class="{ 'todo-tile--idle': item.count === 0 }"
            :data-testid="`todo-${item.key}`"
          >
            <span class="todo-tile__head">
              <q-icon :name="item.icon" size="18px" class="todo-tile__icon" />
              <span class="todo-tile__label">{{ item.label }}</span>
            </span>
            <span class="todo-tile__count font-mono">{{ item.count }}</span>
            <span class="todo-tile__hint">
              <template v-if="item.count === 0">
                <q-icon name="ph:check" size="14px" /> {{ $t('dashboard.nothing') }}
              </template>
              <template v-else>{{ item.hint }}</template>
            </span>
          </router-link>
        </template>
        <template v-else-if="loading">
          <q-skeleton v-for="n in 4" :key="n" type="rect" class="todo-skeleton" />
        </template>
      </div>
    </section>

    <div class="dashboard-columns">
      <section class="app-section" aria-labelledby="activity-title">
        <div class="app-section__head">
          <h2 id="activity-title" class="app-section__title">{{ $t('dashboard.activity') }}</h2>
        </div>
        <div v-if="data" class="kpi-grid">
          <component
            :is="kpi.to ? 'router-link' : 'div'"
            v-for="kpi in kpis"
            :key="kpi.label"
            :to="kpi.to"
            class="kpi"
            :class="{ 'kpi--link': kpi.to }"
          >
            <span class="kpi__label">{{ kpi.label }}</span>
            <span class="kpi__value font-mono">{{ kpi.value }}</span>
            <span v-if="kpi.hint" class="kpi__hint">{{ kpi.hint }}</span>
          </component>
        </div>
        <q-skeleton v-else-if="loading" type="rect" height="120px" />
      </section>

      <section
        v-if="shopConfig.moduleOn('grouped_departures')"
        class="app-section"
        aria-labelledby="departure-title"
      >
        <div class="app-section__head">
          <h2 id="departure-title" class="app-section__title">
            {{ $t('dashboard.next_departure') }}
          </h2>
          <router-link to="/grouped-departures" class="app-section__action text-link">
            {{ $t('dashboard.all_departures') }}
          </router-link>
        </div>
        <div v-if="data?.next_departure" class="app-panel departure">
          <div class="departure__head">
            <span class="departure__label">{{ data.next_departure.label }}</span>
            <StatusTag
              v-if="data.next_departure.status === 'draft'"
              tone="neutral"
              icon="ph:pencil-simple"
              :label="$t('dashboard.draft')"
            />
            <StatusTag v-else tone="ok" icon="ph:check-circle" :label="$t('dashboard.open')" />
          </div>
          <dl class="admin-dl">
            <dt>{{ $t('dashboard.cutoff') }}</dt>
            <dd>{{ formatDateTime(data.next_departure.cutoff_at) || '—' }}</dd>
            <dt>{{ $t('dashboard.departure') }}</dt>
            <dd>{{ formatDate(data.next_departure.departure_at) || '—' }}</dd>
            <dt>{{ $t('dashboard.linked_orders') }}</dt>
            <dd class="font-mono">{{ data.next_departure.orders_count }}</dd>
          </dl>
        </div>
        <div v-else-if="data" class="app-empty">
          <q-icon name="ph:calendar-blank" size="28px" class="text-subtle" />
          <p>{{ $t('dashboard.no_departure') }}</p>
        </div>
        <q-skeleton v-else-if="loading" type="rect" height="120px" />
      </section>
    </div>

    <section class="app-section" aria-labelledby="shortcuts-title">
      <div class="app-section__head">
        <h2 id="shortcuts-title" class="app-section__title">{{ $t('dashboard.shortcuts') }}</h2>
      </div>
      <nav class="shortcuts">
        <router-link v-for="link in shortcuts" :key="link.to" :to="link.to" class="shortcut">
          <q-icon :name="link.icon" size="18px" />
          {{ link.label }}
          <q-icon name="ph:arrow-right" size="14px" class="shortcut__arrow" />
        </router-link>
      </nav>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { formatDate, formatDateTime, formatMoney, intlLocale } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import {
  getDashboard,
  getSetupChecklist,
  type AdminDashboard,
  type DashboardTodo,
  type SetupChecklist,
  type SetupChecklistItem,
} from '@/api/dashboard';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();

const shopConfig = useShopConfigStore();
const data = ref<AdminDashboard | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
/** Mise en route : visible tant qu'un point reste à faire ou à confirmer. */
const checklist = ref<SetupChecklist | null>(null);
const checklistComplete = computed(
  () => checklist.value?.items.every((item) => item.status === 'done') ?? true,
);
const SETUP_ICONS: Record<SetupChecklistItem['status'], string> = {
  done: 'ph:check-circle',
  todo: 'ph:circle-dashed',
  check: 'ph:warning-circle',
};
const SETUP_TONES: Record<SetupChecklistItem['status'], 'ok' | 'warn' | 'danger'> = {
  done: 'ok',
  todo: 'danger',
  check: 'warn',
};

const today = new Intl.DateTimeFormat(intlLocale(), {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
}).format(new Date());

interface TodoItem {
  key: keyof DashboardTodo;
  label: string;
  hint: string;
  icon: string;
  to: string;
  /** Module dont dépend la file (masquée quand il est éteint). */
  module?: string;
}

const TODO = computed<TodoItem[]>(() => [
  {
    key: 'orders_to_process',
    label: t('dashboard.t_orders'),
    hint: t('dashboard.t_orders_hint'),
    icon: 'ph:receipt',
    to: '/orders',
  },
  {
    key: 'payments_to_validate',
    label: t('dashboard.t_payments'),
    hint: t('dashboard.t_payments_hint'),
    icon: 'ph:check-square-offset',
    to: '/payment-validations',
  },
  {
    key: 'payments_to_capture',
    label: t('dashboard.t_capture'),
    hint: t('dashboard.t_capture_hint'),
    icon: 'ph:credit-card',
    to: '/payments?status=Authorized',
  },
  {
    key: 'quote_requests_open',
    label: t('dashboard.t_quotes'),
    hint: t('dashboard.t_quotes_hint'),
    icon: 'ph:note-pencil',
    to: '/quote-requests',
    module: 'quotes',
  },
  {
    key: 'group_upgrade_requests_pending',
    label: t('dashboard.t_groups'),
    hint: t('dashboard.t_groups_hint'),
    icon: 'ph:user-plus',
    to: '/group-upgrade-requests',
    module: 'price_groups',
  },
  {
    key: 'supplier_orders_draft',
    label: t('dashboard.t_supplier'),
    hint: t('dashboard.t_supplier_hint'),
    icon: 'ph:clipboard-text',
    to: '/supplier-orders',
    module: 'supplier_orders',
  },
  {
    key: 'product_drafts',
    label: t('dashboard.t_review'),
    hint: t('dashboard.t_review_hint'),
    icon: 'ph:package',
    to: '/products',
    module: 'suppliers',
  },
]);

const todoItems = computed(() => {
  const todo = data.value?.todo;
  if (!todo) return [];
  return TODO.value
    .filter((item) => !item.module || shopConfig.moduleOn(item.module))
    .map((item) => ({
      ...item,
      count: todo[item.key] ?? 0,
    }));
});

const pendingTotal = computed(() => todoItems.value.reduce((sum, item) => sum + item.count, 0));

interface Kpi {
  label: string;
  value: string;
  hint?: string;
  to?: string;
}

const kpis = computed<Kpi[]>(() => {
  const activity = data.value?.activity;
  const stock = data.value?.stock;
  if (!activity || !stock) return [];
  const money = (value: string) => formatMoney(value, activity.currency);
  const percent = new Intl.NumberFormat(intlLocale(), { maximumFractionDigits: 1 });
  return [
    { label: t('dashboard.k_today'), value: String(activity.orders_today) },
    { label: t('dashboard.k_7d'), value: String(activity.orders_7d) },
    { label: t('dashboard.k_rev7'), value: money(activity.revenue_7d) },
    { label: t('dashboard.k_rev30'), value: money(activity.revenue_30d) },
    // R8 / U7 : the month's figures a shop compares month to month.
    { label: t('dashboard.k_30d'), value: String(activity.orders_30d) },
    {
      label: t('dashboard.k_basket'),
      value: activity.average_basket_30d != null ? money(activity.average_basket_30d) : '—',
    },
    {
      label: t('dashboard.k_conversion'),
      value:
        activity.conversion_30d_pct != null
          ? `${percent.format(Number(activity.conversion_30d_pct))} %`
          : '—',
      hint: t('dashboard.k_conversion_hint', {
        ordered: activity.carts_ordered_30d,
        carts: activity.carts_30d,
      }),
    },
    {
      label: t('dashboard.k_low_stock', { n: stock.low_stock_threshold }),
      value: String(stock.low_stock),
      hint: t('dashboard.k_out_of_stock', { n: stock.out_of_stock }),
      to: '/inventory',
    },
  ];
});

const shortcuts = computed(() => [
  { label: t('dashboard.s_products'), icon: 'ph:package', to: '/products' },
  { label: t('dashboard.s_orders'), icon: 'ph:receipt', to: '/orders' },
  { label: t('dashboard.s_home'), icon: 'ph:house', to: '/homepage' },
  { label: t('dashboard.s_settings'), icon: 'ph:gear', to: '/system-settings' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  // The checklist is a help, not the page: its failure never hides the rest.
  void getSetupChecklist()
    .then((result) => (checklist.value = result))
    .catch(() => (checklist.value = null));
  try {
    data.value = await getDashboard();
  } catch (err) {
    error.value = extractApiError(err) ?? t('dashboard.load_failed');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void shopConfig.load();
  void load();
});
</script>

<style scoped lang="scss">
.setup-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  overflow: hidden;

  li + li {
    border-top: 1px solid var(--n-line);
  }
}

.setup-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  color: inherit;
  text-decoration: none;

  &:hover,
  &:focus-visible {
    background: var(--n-tile-hover);
  }
}

.setup-item__icon {
  flex: none;
}

.setup-item--done .setup-item__icon {
  color: var(--n-ok);
}

.setup-item--todo .setup-item__icon {
  color: var(--n-danger);
}

.setup-item--check .setup-item__icon {
  color: var(--n-warn);
}

.setup-item__text {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.setup-item__hint {
  color: var(--n-ink-3);
  font-size: 0.875rem;
}

.todo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;

  @media (max-width: 599px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
}

.todo-skeleton {
  height: 132px;
  border-radius: var(--n-radius);
}

.todo-tile {
  min-height: 132px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: inherit;
  text-decoration: none;
}

.kpi--link:hover,
.kpi--link:focus-visible {
  background: var(--n-tile-hover);
}

.kpi__hint {
  font-size: 12px;
  color: var(--n-ink-3);
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  background: var(--n-surface);
  color: var(--n-ink);
  text-decoration: none;
  transition:
    border-color 0.15s ease,
    transform 0.16s cubic-bezier(0.16, 1, 0.3, 1);

  &:hover {
    border-color: var(--n-ink-3);
  }

  &:active {
    transform: translateY(1px);
  }

  &--idle {
    background: transparent;

    .todo-tile__count {
      color: var(--n-ink-3);
    }
  }
}

.todo-tile__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.todo-tile__icon {
  color: var(--n-ink-3);

  .todo-tile:not(.todo-tile--idle) & {
    color: var(--n-accent);
  }
}

.todo-tile__label {
  font-size: 13.5px;
  font-weight: 500;
}

.todo-tile__count {
  margin-top: auto;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.todo-tile__hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  color: var(--n-ink-3);
}

@media (max-width: 599px) {
  .todo-tile {
    min-height: 0;
    padding: 12px 14px;
  }

  .todo-tile__count {
    font-size: 24px;
  }

  .todo-tile__hint {
    display: none;
  }
}

.dashboard-columns {
  margin-top: 48px;
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 48px 32px;

  .app-section + .app-section {
    margin-top: 0;
  }

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
  }
}

.dashboard-columns + .app-section {
  margin-top: 48px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--n-line);
  border-left: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  overflow: hidden;
}

.kpi {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-right: 1px solid var(--n-line);
  border-bottom: 1px solid var(--n-line);
  background: var(--n-surface);

  &:nth-child(2) {
    border-top-right-radius: 8px;
  }
}

.kpi__label {
  font-size: 12.5px;
  color: var(--n-ink-3);
}

.kpi__value {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.departure__head {
  margin-bottom: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.departure__label {
  font-size: 16px;
  font-weight: 600;
}

.shortcuts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shortcut {
  padding: 9px 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  color: var(--n-ink);
  font-size: 13.5px;
  text-decoration: none;

  &:hover {
    border-color: var(--n-ink-3);

    .shortcut__arrow {
      transform: translateX(2px);
    }
  }
}

.shortcut__arrow {
  color: var(--n-ink-3);
  transition: transform 0.16s ease;
}
</style>
