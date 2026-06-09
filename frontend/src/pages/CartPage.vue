<template>
  <q-page class="cart-page q-pa-md">
    <div class="row items-center q-mb-md">
      <div class="col">
        <h1 class="text-h5 q-my-none">Mon panier</h1>
      </div>
      <div class="col-auto">
        <q-btn
          flat
          color="primary"
          icon="storefront"
          label="Continuer mes achats"
          :to="{ name: 'catalogue' }"
        />
      </div>
    </div>

    <q-banner
      v-if="cartStore.error"
      class="bg-red-1 text-red-8 q-mb-md"
      rounded
    >
      <template #avatar><q-icon name="error_outline" /></template>
      {{ cartStore.error }}
      <template #action>
        <q-btn flat label="Réessayer" @click="loadCart" />
      </template>
    </q-banner>

    <div class="row q-col-gutter-lg">
      <div class="col-12 col-lg-8">
        <q-card v-if="cartStore.loading" flat bordered>
          <q-list>
            <q-item v-for="n in 3" :key="n">
              <q-item-section avatar>
                <q-skeleton square size="72px" />
              </q-item-section>
              <q-item-section>
                <q-skeleton type="text" width="55%" />
                <q-skeleton type="text" width="35%" />
              </q-item-section>
              <q-item-section side>
                <q-skeleton type="text" width="80px" />
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>

        <q-card
          v-else-if="cartStore.items.length === 0"
          flat
          bordered
          class="column items-center q-py-xl text-grey-7"
        >
          <q-icon name="remove_shopping_cart" size="4rem" class="q-mb-sm" />
          <div class="text-h6">Votre panier est vide</div>
          <div class="text-body2 q-mt-xs">Ajoutez des produits depuis le catalogue.</div>
        </q-card>

        <q-card v-else flat bordered>
          <q-list separator>
            <q-item
              v-for="entry in cartStore.detailedItems"
              :key="entry.item.id"
              class="q-py-md"
            >
              <q-item-section avatar top>
                <q-img
                  :src="entry.product?.image_url ?? entry.product?.supplier_image_url ?? placeholderImg"
                  width="72px"
                  height="72px"
                  fit="contain"
                  class="rounded-borders bg-grey-1"
                />
              </q-item-section>

              <q-item-section>
                <div class="text-subtitle2 text-weight-medium">
                  {{ entry.product?.name ?? fallbackProductName(entry.item.product_id) }}
                </div>
                <div v-if="entry.product?.vendor_part_number" class="text-caption text-grey-6">
                  Réf. {{ entry.product.vendor_part_number }}
                </div>
                <div class="text-caption text-grey-7 q-mt-xs">
                  Prix unitaire: {{ moneyLabel(entry.item.unit_price) }}
                </div>
              </q-item-section>

              <q-item-section side top class="items-end">
                <div class="row items-center q-gutter-xs q-mb-sm">
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="remove"
                    :disable="cartStore.mutating"
                    @click="decreaseQuantity(entry.item.id, entry.item.quantity)"
                  />
                  <div class="text-body2 text-weight-medium cart-qty">
                    {{ entry.item.quantity }}
                  </div>
                  <q-btn
                    flat
                    round
                    dense
                    size="sm"
                    icon="add"
                    :disable="cartStore.mutating"
                    @click="increaseQuantity(entry.item.id, entry.item.quantity)"
                  />
                </div>

                <div class="text-subtitle2 text-weight-bold q-mb-xs">
                  {{ moneyLabel(entry.item.line_total) }}
                </div>

                <q-btn
                  flat
                  dense
                  color="negative"
                  icon="delete_outline"
                  label="Supprimer"
                  :disable="cartStore.mutating"
                  @click="removeItem(entry.item.id)"
                />
              </q-item-section>
            </q-item>
          </q-list>
        </q-card>
      </div>

      <div class="col-12 col-lg-4">
        <q-card flat bordered class="q-pa-md summary-card">
          <div class="text-h6 q-mb-sm">Commander</div>

          <div class="row justify-between text-body2 q-mb-xs">
            <span>Articles</span>
            <strong>{{ cartStore.totalItems }}</strong>
          </div>
          <div class="row justify-between text-body2 q-mb-sm">
            <span>Total panier</span>
            <strong>{{ moneyNumberLabel(cartStore.totalAmount) }}</strong>
          </div>

          <q-separator class="q-my-md" />

          <q-btn
            unelevated
            color="positive"
            icon="credit_card"
            label="Payer par carte bancaire"
            class="full-width q-mb-sm"
            :disable="cartStore.items.length === 0 || cartStore.mutating"
            @click="goToCheckout"
          />

          <q-btn
            flat
            color="grey-7"
            icon="delete_sweep"
            label="Vider le panier"
            class="full-width"
            :disable="cartStore.items.length === 0 || cartStore.mutating"
            @click="clearCart"
          />
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { formatXpf } from '@app/utils'
import { useCartStore } from 'src/stores/cart'

const cartStore = useCartStore()
const router = useRouter()

const placeholderImg = '/icons/placeholder-product.svg'

function parseMoney(raw: string): number {
  const value = Number.parseFloat(raw)
  return Number.isFinite(value) ? value : 0
}

function moneyLabel(raw: string): string {
  return formatXpf(parseMoney(raw))
}

function moneyNumberLabel(amount: number): string {
  return formatXpf(amount)
}

function fallbackProductName(productId: string): string {
  return `Produit ${productId.slice(0, 8)}`
}

async function loadCart() {
  await cartStore.loadCart()
}

function increaseQuantity(itemId: string, currentQuantity: number) {
  cartStore.updateItemQuantity(itemId, currentQuantity + 1)
}

function decreaseQuantity(itemId: string, currentQuantity: number) {
  if (currentQuantity <= 1) {
    cartStore.removeItem(itemId)
    return
  }
  cartStore.updateItemQuantity(itemId, currentQuantity - 1)
}

function removeItem(itemId: string) {
  cartStore.removeItem(itemId)
}

function clearCart() {
  cartStore.clearCart()
}

function goToCheckout() {
  void router.push({ name: 'checkout' })
}

onMounted(async () => {
  await loadCart()
})
</script>

<style scoped lang="scss">
.cart-page {
  max-width: 1240px;
  margin: 0 auto;
}

.cart-qty {
  min-width: 2rem;
  text-align: center;
}

.summary-card {
  position: sticky;
  top: 88px;
}

@media (max-width: 1023px) {
  .summary-card {
    position: static;
  }
}
</style>
