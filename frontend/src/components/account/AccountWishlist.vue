<template>
  <div>
    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">Favoris</h2>
        <p class="app-section__hint">Les produits mis de côté depuis leur fiche.</p>
      </div>

      <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
      <AppNotice v-if="cartError" dense tone="error" class="q-mb-md">{{ cartError }}</AppNotice>

      <div v-if="loading" class="product-grid" aria-busy="true">
        <div v-for="n in 4" :key="n" class="skeleton-card">
          <q-skeleton square class="skeleton-card__media" />
          <q-skeleton type="text" width="80%" />
        </div>
      </div>

      <div v-else-if="!products.length" class="app-empty">
        <q-icon name="ph:heart" size="36px" class="text-subtle" />
        <h3>Aucun favori</h3>
        <p>Sur une fiche produit, « Ajouter aux favoris » le garde ici pour plus tard.</p>
        <q-btn outline color="primary" label="Voir le catalogue" :to="{ name: 'catalogue' }" />
      </div>

      <div v-else class="product-grid" data-testid="account-wishlist">
        <div v-for="product in products" :key="product.id" class="wish">
          <ProductCard :product="product" @add-to-cart="onAddToCart" />
          <button
            type="button"
            class="text-link wish__remove"
            :disabled="removingId === product.id"
            @click="remove(product.id)"
          >
            Retirer des favoris
          </button>
        </div>
      </div>
    </section>

    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">Alertes de disponibilité</h2>
        <p class="app-section__hint">
          Un e-mail vous prévient quand un produit épuisé revient en stock.
        </p>
      </div>

      <div v-if="!alerts.length" class="app-empty">
        <q-icon name="ph:bell" size="36px" class="text-subtle" />
        <h3>Aucune alerte</h3>
        <p>Sur un produit épuisé, « Me prévenir » crée une alerte.</p>
      </div>

      <ul v-else class="app-rows" data-testid="account-stock-alerts">
        <li v-for="alert in alerts" :key="alert.id" class="app-row">
          <q-icon
            :name="alert.status === 'sent' ? 'ph:envelope-simple-open' : 'ph:bell-ringing'"
            size="20px"
            class="text-subtle"
          />
          <div class="app-row__main">
            <router-link
              :to="{ name: 'product-detail', params: { id: alert.product_id } }"
              class="app-row__title"
            >
              {{ alert.product_name ?? 'Produit' }}
            </router-link>
            <span class="app-row__meta">
              {{
                alert.status === 'sent'
                  ? `Prévenu le ${formatDate(alert.notified_at)}`
                  : 'En attente du retour en stock'
              }}
            </span>
          </div>
          <button
            v-if="alert.status === 'pending'"
            type="button"
            class="text-link"
            @click="cancelAlert(alert)"
          >
            Annuler
          </button>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { formatDate } from '@app/utils';
import type { components } from '@app/api-types';

import AppNotice from '@app/ui/AppNotice.vue';
import ProductCard from '@/components/ProductCard.vue';
import { getProductById } from '@/api/products';
import { cancelStockAlert, listMyStockAlerts, type StockAlert } from '@/api/stockAlerts';
import { getMyWishlist, removeFromMyWishlist } from '@/api/wishlist';
import { useCartStore } from '@/stores/cart';
import { useUiStore } from '@/stores/ui';
import { apiErrorMessage } from '@/utils/errors';

type ProductPublic = components['schemas']['ProductPublic'];

const cartStore = useCartStore();
const uiStore = useUiStore();

const products = ref<ProductPublic[]>([]);
const alerts = ref<StockAlert[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const cartError = ref<string | null>(null);
const removingId = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [wishlist, alertList] = await Promise.all([
      getMyWishlist(),
      listMyStockAlerts().catch(() => [] as StockAlert[]),
    ]);
    alerts.value = alertList;
    // Un produit retiré du catalogue depuis disparaît simplement de la liste.
    const results = await Promise.allSettled(
      wishlist.items.map((item) => getProductById(item.product_id)),
    );
    products.value = results
      .filter((r): r is PromiseFulfilledResult<ProductPublic> => r.status === 'fulfilled')
      .map((r) => r.value);
  } catch (err) {
    error.value = apiErrorMessage(err) ?? 'Impossible de charger vos favoris.';
  } finally {
    loading.value = false;
  }
}

async function remove(productId: string) {
  removingId.value = productId;
  try {
    await removeFromMyWishlist(productId);
    products.value = products.value.filter((p) => p.id !== productId);
  } catch (err) {
    error.value = apiErrorMessage(err) ?? 'Impossible de retirer ce favori.';
  } finally {
    removingId.value = null;
  }
}

async function cancelAlert(alert: StockAlert) {
  try {
    await cancelStockAlert(alert.id);
    alerts.value = alerts.value.filter((a) => a.id !== alert.id);
  } catch (err) {
    error.value = apiErrorMessage(err) ?? "Impossible d'annuler cette alerte.";
  }
}

async function onAddToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? "Impossible d'ajouter cet article au panier.";
}

onMounted(load);
</script>

<style scoped lang="scss">
.wish {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wish__remove {
  align-self: flex-start;
}
</style>
