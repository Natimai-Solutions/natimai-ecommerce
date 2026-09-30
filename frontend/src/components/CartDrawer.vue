<template>
  <q-drawer
    v-model="open"
    side="right"
    overlay
    behavior="mobile"
    :width="420"
    class="cart-drawer"
    aria-label="Panier"
  >
    <div class="cart-drawer__inner">
      <header class="cart-drawer__head">
        <q-icon
          v-if="uiStore.lastAddedProductId"
          name="ph:check-circle"
          size="20px"
          class="cart-drawer__check"
        />
        <h2 class="cart-drawer__title">
          {{ uiStore.lastAddedProductId ? 'Ajouté au panier' : 'Panier' }}
        </h2>
        <q-btn flat round dense icon="ph:x" aria-label="Fermer le panier" @click="close" />
      </header>

      <div v-if="lines.length === 0" class="cart-drawer__empty">
        <q-icon name="ph:shopping-bag" size="40px" class="text-subtle" />
        <p>Votre panier est vide.</p>
      </div>

      <ul v-else class="cart-drawer__lines">
        <li v-for="entry in lines" :key="entry.item.id" class="cart-drawer__line">
          <div class="cart-drawer__thumb">
            <ProductImage
              :src="entry.product?.image_url ?? entry.product?.supplier_image_url"
              :alt="entry.product?.name ?? 'Article'"
              glyph-size="28px"
            />
          </div>
          <div class="cart-drawer__desc">
            <span class="cart-drawer__brand">{{ entry.product?.manufacturer ?? '' }}</span>
            <span class="cart-drawer__name">{{ entry.product?.name ?? 'Article' }}</span>
            <span class="cart-drawer__qty font-mono">Qté {{ entry.item.quantity }}</span>
          </div>
          <span class="cart-drawer__price font-mono">
            {{ currencyStore.format(entry.item.line_total) }}
          </span>
        </li>
      </ul>

      <footer class="cart-drawer__foot">
        <div class="cart-drawer__total">
          <span>Sous-total TTC</span>
          <span class="font-mono">{{ currencyStore.format(cartStore.totalAmount) }}</span>
        </div>
        <p class="cart-drawer__note">Frais de livraison calculés à la commande.</p>
        <div class="cart-drawer__actions">
          <q-btn
            unelevated
            color="primary"
            label="Voir le panier"
            :to="{ name: 'cart' }"
            @click="close"
          />
          <q-btn outline color="primary" label="Continuer mes achats" @click="close" />
        </div>
      </footer>
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import ProductImage from '@/components/ProductImage.vue';
import { useCartStore } from '@/stores/cart';
import { useCurrencyStore } from '@/stores/currency';
import { useUiStore } from '@/stores/ui';

const uiStore = useUiStore();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();

const open = computed({
  get: () => uiStore.cartDrawerOpen,
  set: (value: boolean) => {
    if (value) uiStore.openCartDrawer(uiStore.lastAddedProductId);
    else uiStore.closeCartDrawer();
  },
});

// Le dernier article ajouté en tête, le reste dans l'ordre du panier.
const lines = computed(() => {
  const added = uiStore.lastAddedProductId;
  const all = cartStore.detailedItems;
  if (!added) return all;
  return [
    ...all.filter((entry) => entry.item.product_id === added),
    ...all.filter((entry) => entry.item.product_id !== added),
  ];
});

function close() {
  uiStore.closeCartDrawer();
}
</script>

<style scoped lang="scss">
.cart-drawer__inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--n-surface);
  color: var(--n-ink);
}

.cart-drawer__head {
  flex-shrink: 0;
  height: 64px;
  padding: 0 12px 0 24px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--n-line);
}

.cart-drawer__check {
  color: var(--n-accent);
}

.cart-drawer__title {
  flex-grow: 1;
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
}

.cart-drawer__empty {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--n-ink-2);

  p {
    margin: 0;
  }
}

.cart-drawer__lines {
  flex-grow: 1;
  overflow-y: auto;
  margin: 0;
  padding: 8px 24px;
  list-style: none;
}

.cart-drawer__line {
  display: flex;
  gap: 14px;
  padding: 16px 0;

  & + & {
    border-top: 1px solid var(--n-line);
  }
}

.cart-drawer__thumb {
  flex-shrink: 0;
  width: 72px;
}

.cart-drawer__desc {
  flex-grow: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.cart-drawer__brand {
  font-size: 12px;
  color: var(--n-ink-2);
}

.cart-drawer__name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
}

.cart-drawer__qty {
  font-size: 12px;
  color: var(--n-ink-3);
}

.cart-drawer__price {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}

.cart-drawer__foot {
  flex-shrink: 0;
  padding: 24px;
  border-top: 1px solid var(--n-line);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cart-drawer__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 14px;
  color: var(--n-ink-2);

  .font-mono {
    font-size: 18px;
    font-weight: 600;
    color: var(--n-ink);
  }
}

.cart-drawer__note {
  margin: 0;
  font-size: 13px;
  color: var(--n-ink-3);
}

.cart-drawer__actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;

  .q-btn {
    min-height: 48px;
  }
}
</style>
