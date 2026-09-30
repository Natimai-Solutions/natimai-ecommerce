<template>
  <q-page class="cart page-container">
    <div class="cart__head">
      <h1 class="page-title">Panier</h1>
      <span v-if="cartStore.totalItems > 0" class="font-mono text-subtle">
        {{ cartStore.totalItems }} article{{ cartStore.totalItems > 1 ? 's' : '' }}
      </span>
    </div>

    <AppNotice v-if="cartStore.error" tone="error" class="cart__notice">
      {{ cartStore.error }}
      <template #action>
        <q-btn flat label="Réessayer" @click="loadCart" />
      </template>
    </AppNotice>

    <div v-if="cartStore.loading" class="cart__layout" aria-busy="true">
      <div class="cart__lines">
        <div v-for="n in 3" :key="n" class="cart-line">
          <q-skeleton square class="cart-line__skeleton" />
          <div class="cart-line__body">
            <q-skeleton type="text" width="55%" />
            <q-skeleton type="text" width="30%" />
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="cartStore.items.length === 0" class="cart__empty">
      <q-icon name="ph:shopping-bag" size="44px" class="text-subtle" />
      <h2>Votre panier est vide</h2>
      <p>Ajoutez des produits depuis le catalogue.</p>
      <q-btn unelevated color="primary" label="Voir le catalogue" :to="{ name: 'catalogue' }" />
    </div>

    <div v-else class="cart__layout">
      <ul class="cart__lines">
        <li v-for="entry in cartStore.detailedItems" :key="entry.item.id" class="cart-line">
          <router-link
            v-if="entry.product"
            :to="getProductRoute(entry.product)"
            class="cart-line__media"
            tabindex="-1"
            aria-hidden="true"
          >
            <ProductImage
              :src="entry.product.image_url ?? entry.product.supplier_image_url"
              :alt="entry.product.name"
              glyph-size="32px"
            />
          </router-link>
          <div v-else class="cart-line__media">
            <ProductImage :src="null" alt="" glyph-size="32px" />
          </div>

          <div class="cart-line__body">
            <span v-if="entry.product?.manufacturer" class="cart-line__brand">
              {{ entry.product.manufacturer }}
            </span>
            <router-link
              v-if="entry.product"
              :to="getProductRoute(entry.product)"
              class="cart-line__name"
            >
              {{ entry.product.name }}
            </router-link>
            <span v-else class="cart-line__name">
              {{ fallbackProductName(entry.item.product_id) }}
            </span>
            <span class="cart-line__meta font-mono">
              <template v-if="entry.product?.vendor_part_number">
                {{ entry.product.vendor_part_number }} ·
              </template>
              {{ moneyLabel(entry.item.unit_price) }} l'unité
            </span>

            <div class="cart-line__controls">
              <div class="qty" role="group" :aria-label="`Quantité, ${entry.product?.name ?? ''}`">
                <button
                  type="button"
                  class="qty__btn"
                  :aria-label="entry.item.quantity <= 1 ? 'Retirer' : 'Diminuer la quantité'"
                  :disabled="cartStore.mutating"
                  @click="decreaseQuantity(entry.item.id, entry.item.quantity)"
                >
                  <q-icon :name="entry.item.quantity <= 1 ? 'ph:trash' : 'ph:minus'" size="16px" />
                </button>
                <span class="qty__value font-mono" aria-live="polite">
                  {{ entry.item.quantity }}
                </span>
                <button
                  type="button"
                  class="qty__btn"
                  aria-label="Augmenter la quantité"
                  :disabled="cartStore.mutating"
                  @click="increaseQuantity(entry.item.id, entry.item.quantity)"
                >
                  <q-icon name="ph:plus" size="16px" />
                </button>
              </div>
              <button
                type="button"
                class="text-link"
                :disabled="cartStore.mutating"
                @click="removeItem(entry.item.id)"
              >
                Supprimer
              </button>
            </div>
          </div>

          <span class="cart-line__total font-mono">{{ moneyLabel(entry.item.line_total) }}</span>
        </li>
      </ul>

      <aside class="cart__summary" aria-label="Récapitulatif">
        <h2 class="cart__summary-title">Récapitulatif</h2>
        <div class="cart__row">
          <span>Articles</span>
          <span class="font-mono">{{ cartStore.totalItems }}</span>
        </div>
        <div class="cart__row cart__row--total">
          <span>Sous-total TTC</span>
          <span class="font-mono">{{ moneyNumberLabel(cartStore.totalAmount) }}</span>
        </div>
        <p class="cart__note">
          Prix toutes taxes comprises. Frais de livraison calculés à la commande.
        </p>

        <q-btn
          unelevated
          data-testid="cart-checkout"
          color="primary"
          label="Passer commande"
          class="cart__checkout"
          :disable="cartStore.items.length === 0 || cartStore.mutating"
          @click="goToCheckout"
        />
        <q-btn
          outline
          color="primary"
          label="Continuer mes achats"
          class="cart__continue"
          :to="{ name: 'catalogue' }"
        />
        <button
          type="button"
          class="text-link cart__clear"
          :disabled="cartStore.mutating"
          @click="clearCart"
        >
          Vider le panier
        </button>
      </aside>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import AppNotice from '@app/ui/AppNotice.vue';
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useCartStore } from '@/stores/cart';
import { useCurrencyStore } from '@/stores/currency';
import ProductImage from '@/components/ProductImage.vue';
import { getProductRoute } from '@/utils/productRoute';

const cartStore = useCartStore();
const currencyStore = useCurrencyStore();
const router = useRouter();

function parseMoney(raw: string): number {
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : 0;
}

function moneyLabel(raw: string): string {
  return currencyStore.format(parseMoney(raw));
}

function moneyNumberLabel(amount: number): string {
  return currencyStore.format(amount);
}

function fallbackProductName(productId: string): string {
  return `Produit ${productId.slice(0, 8)}`;
}

async function loadCart() {
  await cartStore.loadCart();
}

function increaseQuantity(itemId: string, currentQuantity: number) {
  cartStore.updateItemQuantity(itemId, currentQuantity + 1);
}

function decreaseQuantity(itemId: string, currentQuantity: number) {
  if (currentQuantity <= 1) {
    cartStore.removeItem(itemId);
    return;
  }
  cartStore.updateItemQuantity(itemId, currentQuantity - 1);
}

function removeItem(itemId: string) {
  cartStore.removeItem(itemId);
}

function clearCart() {
  cartStore.clearCart();
}

function goToCheckout() {
  void router.push({ name: 'checkout' });
}

onMounted(async () => {
  await loadCart();
});
</script>

<style scoped lang="scss">
.cart {
  padding-top: 32px;
  padding-bottom: 96px;
}

.cart__head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 28px;
}

.cart__notice {
  margin-bottom: 24px;
}

.cart__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 64px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 40px;
  }
}

.cart__lines {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--n-line);
}

.cart-line {
  padding: 24px 0;
  display: flex;
  gap: 20px;
  border-bottom: 1px solid var(--n-line);

  @media (max-width: 767px) {
    gap: 14px;
    flex-wrap: wrap;
  }
}

.cart-line__media {
  flex-shrink: 0;
  width: 112px;
  display: block;

  @media (max-width: 767px) {
    width: 80px;
  }
}

.cart-line__skeleton {
  width: 112px;
  height: 112px;
  border-radius: 8px;
}

.cart-line__body {
  flex-grow: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  @media (max-width: 767px) {
    flex-basis: calc(100% - 94px);
  }
}

.cart-line__brand {
  font-size: 13px;
  color: var(--n-ink-2);
}

.cart-line__name {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.35;
  color: var(--n-ink);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.cart-line__meta {
  font-size: 12px;
  color: var(--n-ink-3);
}

.cart-line__controls {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.cart-line__total {
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;

  @media (max-width: 767px) {
    margin-left: 94px;
  }
}

.qty {
  height: 40px;
  display: flex;
  align-items: center;
  border: 1px solid var(--n-line-2);
  border-radius: 8px;
}

.qty__btn {
  width: 40px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--n-ink);
  cursor: pointer;

  &:hover:not(:disabled) {
    background: var(--n-tile);
  }

  &:disabled {
    color: var(--n-line-2);
    cursor: default;
  }
}

.qty__value {
  min-width: 28px;
  text-align: center;
  font-size: 14px;
  font-weight: 500;
}

.cart__summary {
  position: sticky;
  top: 88px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-radius: 8px;
  background: var(--n-tile);

  @media (max-width: 1023px) {
    position: static;
  }
}

.cart__summary-title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}

.cart__row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 14px;
  color: var(--n-ink-2);

  &--total {
    padding-top: 12px;
    border-top: 1px solid var(--n-line-2);
    color: var(--n-ink);

    .font-mono {
      font-size: 20px;
      font-weight: 600;
    }
  }
}

.cart__note {
  margin: 0;
  font-size: 13px;
  color: var(--n-ink-3);
}

.cart__checkout,
.cart__continue {
  min-height: 48px;
}

.cart__checkout {
  margin-top: 8px;
}

.cart__clear {
  align-self: center;
  margin-top: 4px;
}

.cart__empty {
  padding: 80px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  text-align: center;

  h2 {
    margin: 8px 0 0;
    font-size: 20px;
    font-weight: 600;
    line-height: 1.3;
  }

  p {
    margin: 0 0 16px;
    color: var(--n-ink-2);
  }

  .q-btn {
    min-height: 48px;
    padding: 0 24px;
  }
}
</style>
