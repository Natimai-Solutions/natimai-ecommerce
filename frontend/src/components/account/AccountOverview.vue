<template>
  <div>
    <section v-if="todo.length" class="app-section" aria-labelledby="overview-todo">
      <div class="app-section__head">
        <h2 id="overview-todo" class="app-section__title">À faire</h2>
      </div>
      <ul class="app-rows" data-testid="account-todo">
        <li v-for="item in todo" :key="item.order.id" class="app-row">
          <q-icon :name="item.icon" size="22px" class="overview__todo-icon" />
          <div class="app-row__main">
            <span class="app-row__title">{{ item.title }}</span>
            <span class="app-row__meta">
              <span class="font-mono">{{ orderRef(item.order.order_number, item.order.id) }}</span>
              · {{ item.detail }}
            </span>
          </div>
          <q-btn unelevated color="primary" :label="item.action" :to="item.to" />
        </li>
      </ul>
    </section>

    <section class="app-section" aria-labelledby="overview-orders">
      <div class="app-section__head">
        <h2 id="overview-orders" class="app-section__title">Dernières commandes</h2>
        <router-link
          v-if="orders.length"
          :to="{ name: 'account', query: { tab: 'orders' } }"
          class="text-link app-section__action"
        >
          Toutes les commandes
        </router-link>
      </div>

      <AppNotice v-if="error" tone="error">{{ error }}</AppNotice>

      <ul v-else-if="loading" class="app-rows" aria-busy="true">
        <li v-for="n in 2" :key="n" class="app-row">
          <div class="app-row__main">
            <q-skeleton type="text" width="30%" /><q-skeleton type="text" width="50%" />
          </div>
        </li>
      </ul>

      <div v-else-if="!orders.length" class="app-empty">
        <q-icon name="ph:receipt" size="36px" class="text-subtle" />
        <h3>Pas encore de commande</h3>
        <p>Le suivi, les factures et les devis de vos commandes se retrouvent ici.</p>
        <q-btn unelevated color="primary" label="Voir le catalogue" :to="{ name: 'catalogue' }" />
      </div>

      <ul v-else class="app-rows">
        <li v-for="order in orders" :key="order.id" class="app-row">
          <div class="app-row__main">
            <router-link
              :to="{ name: 'order-tracking', params: { id: order.id } }"
              class="app-row__title font-mono"
            >
              {{ orderRef(order.order_number, order.id) }}
            </router-link>
            <span class="app-row__meta">{{ formatDate(order.created_at) }}</span>
          </div>
          <StatusTag
            :tone="facet(order).tone"
            :icon="facet(order).icon"
            :label="facet(order).label"
          />
          <span class="font-mono overview__amount">
            {{ orderMoney(order.total_amount, order.currency, currencyStore.reference) }}
          </span>
        </li>
      </ul>
    </section>

    <section class="app-section" aria-labelledby="overview-shortcuts">
      <h2 id="overview-shortcuts" class="sr-only">Raccourcis</h2>
      <ul class="shortcuts">
        <li v-for="link in shortcuts" :key="link.tab">
          <router-link :to="{ name: 'account', query: { tab: link.tab } }" class="shortcut">
            <q-icon :name="link.icon" size="22px" class="shortcut__icon" />
            <span class="shortcut__label">{{ link.label }}</span>
            <span class="shortcut__hint">{{ link.hint }}</span>
          </router-link>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import type { RouteLocationRaw } from 'vue-router';
import { formatDate, orderRef } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { listMyOrders, type Order } from '@/api/orders';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';
import { deliveryFacet, paymentFacet, type StatusFacet } from '@/utils/orderStatus';

const currencyStore = useCurrencyStore();

const orders = ref<Order[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

function facet(order: Order): StatusFacet {
  return deliveryFacet(order.order_status_name) ?? paymentFacet(order.order_status_name);
}

interface TodoItem {
  order: Order;
  icon: string;
  title: string;
  detail: string;
  action: string;
  to: RouteLocationRaw;
}

/** Ce qui attend le client : un solde demandé, un paiement à envoyer. */
const todo = computed<TodoItem[]>(() => {
  const items: TodoItem[] = [];
  for (const order of orders.value) {
    const amount = (raw: string) => orderMoney(raw, order.currency, currencyStore.reference);
    if (order.balance_due) {
      items.push({
        order,
        icon: 'ph:coins',
        title: 'Solde à régler',
        detail: `${amount(order.balance_amount)} : vos articles sont arrivés.`,
        action: 'Régler le solde',
        to: { name: 'order-balance', params: { id: order.id } },
      });
    } else if (order.order_status_name === 'AwaitingPayment') {
      items.push({
        order,
        icon: 'ph:clock',
        title: 'Paiement attendu',
        detail: `${amount(order.total_amount)} : la commande part dès réception du règlement.`,
        action: 'Voir la commande',
        to: { name: 'order-tracking', params: { id: order.id } },
      });
    }
  }
  return items;
});

const shortcuts = [
  { tab: 'addresses', icon: 'ph:map-pin', label: 'Adresses', hint: 'Livraison et facturation' },
  { tab: 'wishlist', icon: 'ph:heart', label: 'Favoris', hint: 'Produits mis de côté' },
  { tab: 'profile', icon: 'ph:user', label: 'Profil', hint: 'Coordonnées, mot de passe' },
  {
    tab: 'preferences',
    icon: 'ph:sliders-horizontal',
    label: 'Préférences',
    hint: 'E-mails, livraison',
  },
];

onMounted(async () => {
  try {
    // Les commandes récentes suffisent : un solde demandé est toujours récent.
    orders.value = await listMyOrders({ limit: 5 });
  } catch (err) {
    error.value = apiErrorMessage(err) ?? 'Impossible de charger vos commandes.';
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped lang="scss">
.overview__todo-icon {
  color: var(--n-accent);
}

.overview__amount {
  min-width: 96px;
  text-align: right;
  font-weight: 600;
  white-space: nowrap;
}

.shortcuts {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.shortcut {
  height: 100%;
  padding: 18px;
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 12px;
  row-gap: 2px;
  align-items: center;
  border-radius: 8px;
  background: var(--n-tile);
  color: var(--n-ink);
  text-decoration: none;
  transition: background-color 0.2s ease;

  &:hover {
    background: var(--n-tile-hover);
  }
}

.shortcut__icon {
  grid-row: span 2;
  color: var(--n-ink-2);
}

.shortcut__label {
  font-size: 15px;
  font-weight: 500;
}

.shortcut__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}
</style>
