<template>
  <q-page class="admin-page">
    <PageHeader title="Tableau de bord" :hint="today">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-lg">
      {{ error }}
      <template #action>
        <q-btn flat dense no-caps label="Réessayer" @click="load" />
      </template>
    </AppNotice>

    <section class="app-section" aria-labelledby="todo-title">
      <div class="app-section__head">
        <h2 id="todo-title" class="app-section__title">À traiter</h2>
        <p v-if="data" class="app-section__hint">
          {{
            pendingTotal
              ? `${pendingTotal} élément${pendingTotal > 1 ? 's' : ''} en attente`
              : 'Tout est à jour'
          }}
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
                <q-icon name="ph:check" size="14px" /> Rien en attente
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
          <h2 id="activity-title" class="app-section__title">Activité</h2>
        </div>
        <div v-if="data" class="kpi-grid">
          <div v-for="kpi in kpis" :key="kpi.label" class="kpi">
            <span class="kpi__label">{{ kpi.label }}</span>
            <span class="kpi__value font-mono">{{ kpi.value }}</span>
          </div>
        </div>
        <q-skeleton v-else-if="loading" type="rect" height="120px" />
      </section>

      <section class="app-section" aria-labelledby="departure-title">
        <div class="app-section__head">
          <h2 id="departure-title" class="app-section__title">Prochain départ</h2>
          <router-link to="/grouped-departures" class="app-section__action text-link">
            Tous les départs
          </router-link>
        </div>
        <div v-if="data?.next_departure" class="app-panel departure">
          <div class="departure__head">
            <span class="departure__label">{{ data.next_departure.label }}</span>
            <StatusTag
              v-if="data.next_departure.status === 'draft'"
              tone="neutral"
              icon="ph:pencil-simple"
              label="Brouillon"
            />
            <StatusTag v-else tone="ok" icon="ph:check-circle" label="Ouvert" />
          </div>
          <dl class="admin-dl">
            <dt>Clôture des commandes</dt>
            <dd>{{ formatDateTime(data.next_departure.cutoff_at) || '—' }}</dd>
            <dt>Départ</dt>
            <dd>{{ formatDate(data.next_departure.departure_at) || '—' }}</dd>
            <dt>Commandes rattachées</dt>
            <dd class="font-mono">{{ data.next_departure.orders_count }}</dd>
          </dl>
        </div>
        <div v-else-if="data" class="app-empty">
          <q-icon name="ph:calendar-blank" size="28px" class="text-subtle" />
          <p>Aucun départ groupé ouvert ou programmé.</p>
        </div>
        <q-skeleton v-else-if="loading" type="rect" height="120px" />
      </section>
    </div>

    <section class="app-section" aria-labelledby="shortcuts-title">
      <div class="app-section__head">
        <h2 id="shortcuts-title" class="app-section__title">Raccourcis</h2>
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
import { computed, onMounted, ref } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { formatDate, formatDateTime, formatMoney } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { getDashboard, type AdminDashboard, type DashboardTodo } from '@/api/dashboard';
import { useShopConfigStore } from '@/stores/shopConfig';

const shopConfig = useShopConfigStore();
const data = ref<AdminDashboard | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const today = new Intl.DateTimeFormat('fr-FR', {
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
  /** Masqué en mode simple (fournisseurs, synchronisation). */
  fullOnly?: boolean;
}

const TODO: TodoItem[] = [
  {
    key: 'orders_to_process',
    label: 'Commandes à préparer',
    hint: 'Payées, pas encore expédiées',
    icon: 'ph:receipt',
    to: '/orders',
  },
  {
    key: 'payments_to_validate',
    label: 'Paiements à valider',
    hint: 'Virements, chèques ou espèces à confirmer',
    icon: 'ph:check-square-offset',
    to: '/payment-validations',
  },
  {
    key: 'quote_requests_open',
    label: 'Demandes de devis',
    hint: 'Demandes ouvertes sans réponse finale',
    icon: 'ph:note-pencil',
    to: '/quote-requests',
  },
  {
    key: 'group_upgrade_requests_pending',
    label: 'Demandes de groupe',
    hint: 'Clients qui demandent un tarif professionnel',
    icon: 'ph:user-plus',
    to: '/group-upgrade-requests',
  },
  {
    key: 'supplier_orders_draft',
    label: 'Commandes fournisseurs',
    hint: 'Brouillons pas encore envoyés',
    icon: 'ph:clipboard-text',
    to: '/supplier-orders',
    fullOnly: true,
  },
  {
    key: 'product_drafts',
    label: 'Produits à relire',
    hint: 'Brouillons issus des fournisseurs',
    icon: 'ph:package',
    to: '/products',
    fullOnly: true,
  },
];

const todoItems = computed(() => {
  const todo = data.value?.todo;
  if (!todo) return [];
  return TODO.filter((item) => !(item.fullOnly && shopConfig.isSimple)).map((item) => ({
    ...item,
    count: todo[item.key] ?? 0,
  }));
});

const pendingTotal = computed(() => todoItems.value.reduce((sum, item) => sum + item.count, 0));

const kpis = computed(() => {
  const activity = data.value?.activity;
  if (!activity) return [];
  const money = (value: string) => formatMoney(value, activity.currency);
  return [
    { label: "Commandes aujourd'hui", value: String(activity.orders_today) },
    { label: 'Commandes sur 7 jours', value: String(activity.orders_7d) },
    { label: "Chiffre d'affaires 7 jours", value: money(activity.revenue_7d) },
    { label: "Chiffre d'affaires 30 jours", value: money(activity.revenue_30d) },
  ];
});

const shortcuts = [
  { label: 'Produits', icon: 'ph:package', to: '/products' },
  { label: 'Commandes', icon: 'ph:receipt', to: '/orders' },
  { label: 'Accueil du site', icon: 'ph:house', to: '/homepage' },
  { label: 'Paramètres', icon: 'ph:gear', to: '/system-settings' },
];

async function load() {
  loading.value = true;
  error.value = null;
  try {
    data.value = await getDashboard();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Le tableau de bord ne peut pas être chargé.';
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
  border-radius: 8px;
}

.todo-tile {
  min-height: 132px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
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
  border-radius: 8px;
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
  border-radius: 8px;
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
