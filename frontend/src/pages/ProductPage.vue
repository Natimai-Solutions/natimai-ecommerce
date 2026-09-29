<template>
  <q-page class="product page-container">
    <nav class="product__crumbs" aria-label="Fil d'Ariane">
      <router-link :to="{ name: 'catalogue' }">Catalogue</router-link>
      <template v-if="categoryLabel && product?.category_id">
        <q-icon name="ph:caret-right" size="12px" />
        <router-link :to="{ name: 'catalogue', query: { cat: product.category_id } }">
          {{ categoryLabel }}
        </router-link>
      </template>
      <template v-if="product">
        <q-icon name="ph:caret-right" size="12px" />
        <span aria-current="page" class="product__crumb-current">{{ product.name }}</span>
      </template>
    </nav>

    <!-- Chargement : squelette à la forme de la page -->
    <div v-if="loading" class="product__hero" aria-busy="true">
      <q-skeleton square class="product__skeleton-media" />
      <div class="product__buy">
        <q-skeleton type="text" width="20%" />
        <q-skeleton type="text" width="95%" height="36px" />
        <q-skeleton type="text" width="70%" height="36px" />
        <q-skeleton type="text" width="40%" class="q-mt-lg" height="44px" />
        <q-skeleton type="rect" height="48px" class="q-mt-lg" />
      </div>
    </div>

    <AppNotice v-else-if="error" tone="error">
      {{ error }}
      <template #action>
        <q-btn flat label="Retour au catalogue" :to="{ name: 'catalogue' }" />
      </template>
    </AppNotice>

    <template v-else-if="product">
      <section class="product__hero">
        <div class="product__gallery">
          <ProductImage
            :src="mainImage"
            :alt="product.name"
            :ratio="4 / 3"
            glyph-size="120px"
            eager
          />
          <div v-if="gallery.length > 1" class="product__thumbs" role="list" aria-label="Photos">
            <button
              v-for="(url, i) in gallery"
              :key="url"
              type="button"
              role="listitem"
              class="product__thumb"
              :class="{ 'product__thumb--active': url === mainImage }"
              :aria-label="`Photo ${i + 1}`"
              :aria-current="url === mainImage ? 'true' : undefined"
              @click="selectedImage = url"
            >
              <ProductImage :src="url" :alt="''" glyph-size="28px" />
            </button>
          </div>
        </div>

        <div class="product__buy">
          <router-link
            v-if="product.manufacturer"
            :to="{ name: 'catalogue', query: { mfr: product.manufacturer } }"
            class="product__brand"
          >
            {{ product.manufacturer }}
          </router-link>
          <h1 class="product__title">{{ product.name }}</h1>
          <div v-if="product.vendor_part_number || product.ean" class="product__ids font-mono">
            <span v-if="product.vendor_part_number">Réf. {{ product.vendor_part_number }}</span>
            <span v-if="product.ean">EAN {{ product.ean }}</span>
          </div>

          <div class="product__price-block">
            <span v-if="isQuote" class="product__price">Prix sur devis</span>
            <span v-else class="product__price font-mono">{{ displayPrice }}</span>
            <span v-if="selectedMode?.customer_label" class="product__price-note">
              Prix en livraison {{ selectedMode.customer_label.toLowerCase() }}. Le mode se choisit
              à la commande.
            </span>
            <span v-if="isOutOfStock" class="product__stock product__stock--order">
              <span class="stock-dot stock-dot--order" aria-hidden="true" />Sur commande
            </span>
            <span v-else class="product__stock">
              <span class="stock-dot" aria-hidden="true" />{{ stockQuantity }} en stock fournisseur
            </span>
          </div>

          <div class="product__actions">
            <div class="qty" role="group" aria-label="Quantité">
              <button
                type="button"
                class="qty__btn"
                aria-label="Diminuer la quantité"
                :disabled="quantity <= 1"
                @click="setQuantity(quantity - 1)"
              >
                <q-icon name="ph:minus" size="16px" />
              </button>
              <span class="qty__value font-mono" aria-live="polite">{{ quantity }}</span>
              <button
                type="button"
                class="qty__btn"
                aria-label="Augmenter la quantité"
                @click="setQuantity(quantity + 1)"
              >
                <q-icon name="ph:plus" size="16px" />
              </button>
            </div>

            <router-link v-if="justAdded" :to="{ name: 'cart' }" class="product__added">
              <q-icon name="ph:check-circle" size="20px" />
              Ajouté, voir le panier
            </router-link>
            <q-btn
              v-else
              unelevated
              color="primary"
              icon="ph:shopping-bag"
              label="Ajouter au panier"
              class="product__add"
              data-testid="product-page-add-to-cart"
              :disable="isOutOfStock"
              :loading="cartStore.mutating"
              @click="onAddToCart"
            />
          </div>

          <AppNotice v-if="cartError" tone="warning" dense class="q-mt-md">
            {{ cartError }}
          </AppNotice>

          <ProductOffers :offers="offers" class="product__offers" />
        </div>
      </section>

      <section v-if="safeDescription || features.length > 0" class="product__about">
        <div v-if="safeDescription">
          <h2 class="product__h2">Description</h2>
          <!-- eslint-disable-next-line vue/no-v-html -- nettoyé par DOMPurify -->
          <div class="product__description" v-html="safeDescription"></div>
        </div>
        <div v-if="features.length > 0">
          <h2 class="product__h2">Points clés</h2>
          <ul class="product__features">
            <li v-for="(feat, i) in features" :key="i">
              <q-icon name="ph:check" size="18px" class="text-subtle" />
              <span>{{ feat }}</span>
            </li>
          </ul>
        </div>
      </section>

      <section
        v-if="specGroups.length > 0 || showKeySpecs"
        class="product__specs"
        aria-labelledby="specs-title"
      >
        <h2 id="specs-title" class="product__h2">Caractéristiques techniques</h2>
        <dl v-if="showKeySpecs" class="key-specs">
          <div v-for="spec in keySpecs" :key="spec.key" class="key-specs__tile">
            <dt class="key-specs__label">{{ spec.label }}</dt>
            <dd class="key-specs__value tabular-nums">{{ spec.value }}</dd>
          </div>
        </dl>
        <div class="product__spec-groups">
          <div v-for="grp in visibleSpecGroups" :key="grp.group" class="spec-group">
            <h3 class="spec-group__title">{{ grp.group || 'Général' }}</h3>
            <dl class="spec-group__list">
              <div v-for="(spec, i) in grp.specs" :key="i" class="spec-group__row">
                <dt>{{ spec.name }}</dt>
                <dd>{{ spec.value }}{{ spec.unit ? ' ' + spec.unit : '' }}</dd>
              </div>
            </dl>
          </div>
        </div>
        <q-btn
          v-if="hiddenSpecCount > 0"
          outline
          color="primary"
          icon-right="ph:caret-down"
          :label="`Afficher toutes les caractéristiques (${specCount})`"
          class="product__specs-more"
          @click="showAllSpecs = true"
        />
      </section>

      <!-- Barre d'achat mobile, toujours à portée de pouce -->
      <div class="lt-md product__mobile-bar">
        <div class="product__mobile-price">
          <span v-if="isQuote">Prix sur devis</span>
          <span v-else class="font-mono">{{ displayPrice }}</span>
        </div>
        <router-link v-if="justAdded" :to="{ name: 'cart' }" class="product__added">
          <q-icon name="ph:check-circle" size="20px" />
          Voir le panier
        </router-link>
        <q-btn
          v-else
          unelevated
          color="primary"
          label="Ajouter"
          class="product__add"
          :disable="isOutOfStock"
          :loading="cartStore.mutating"
          @click="onAddToCart"
        />
      </div>
    </template>
  </q-page>
</template>
<script setup lang="ts">
import AppNotice from 'src/components/AppNotice.vue';
import DOMPurify from 'isomorphic-dompurify';
import { useMeta } from 'quasar';
import { computed, onBeforeUnmount, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { components } from '@app/api-types';
import {
  getProductById,
  getProductKeySpecs,
  getProductOffers,
  getProductShippingModes,
  type ProductKeySpec,
  type ProductOffersResponse,
  type ShippingModePricePublic,
} from 'src/api/products';
import ProductImage from 'src/components/ProductImage.vue';
import ProductOffers from 'src/components/ProductOffers.vue';
import { useCartStore } from 'src/stores/cart';
import { useProductsStore } from 'src/stores/products';
import { useCurrencyStore } from 'src/stores/currency';
import { getProductRouteByIdAndName, slugifyProductName } from 'src/utils/productRoute';

type ProductPublic = components['schemas']['ProductPublic'];
type Spec = { name: string; value: string; unit: string };

const route = useRoute();
const router = useRouter();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();
const productsStore = useProductsStore();

/** Groupes de caractéristiques affichés avant « Afficher toutes ». */
const SPEC_GROUPS_SHOWN = 3;

const product = ref<ProductPublic | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const cartError = ref<string | null>(null);
const quantity = ref(1);
const justAdded = ref(false);
const showAllSpecs = ref(false);
const selectedImage = ref<string | null>(null);

const shippingModes = ref<ShippingModePricePublic[]>([]);
const selectedModeKey = ref<string | null>(null);
const offers = ref<ProductOffersResponse | null>(null);
const keySpecs = ref<ProductKeySpec[]>([]);

/** Tuiles affichées seulement à partir de deux : une seule ne résume rien. */
const showKeySpecs = computed(() => keySpecs.value.length >= 2);

const isOutOfStock = computed(() => {
  if (!product.value) return true;
  return parseFloat(product.value.supplier_quantity) <= 0;
});

const stockQuantity = computed(() => {
  if (!product.value) return 0;
  return Math.max(0, Math.round(parseFloat(product.value.supplier_quantity)));
});

const selectedMode = computed(
  () => shippingModes.value.find((m) => m.service_level === selectedModeKey.value) ?? null,
);

const priceValue = computed(() => {
  if (selectedMode.value) return parseFloat(selectedMode.value.sale_price);
  return product.value ? parseFloat(product.value.base_price) : 0;
});

/** Prix nul : l'article est vendu sur devis. */
const isQuote = computed(() => !(priceValue.value > 0));

const displayPrice = computed(() => currencyStore.format(priceValue.value));

const categoryLabel = computed(() => {
  const id = product.value?.category_id;
  const cat = id ? productsStore.categories.find((c) => c.id === id) : undefined;
  return cat ? (cat.title ?? cat.name) : null;
});

const safeDescription = computed(() => {
  const raw = product.value?.long_description ?? product.value?.description ?? '';
  return raw ? DOMPurify.sanitize(raw) : '';
});

const plainDescription = computed(() =>
  safeDescription.value
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim(),
);

const features = computed(() =>
  (product.value?.features ?? []).map((f) => String(f).trim()).filter(Boolean),
);

function toStr(v: unknown): string {
  return typeof v === 'string' || typeof v === 'number' ? String(v).trim() : '';
}

const specGroups = computed<{ group: string; specs: Spec[] }[]>(() => {
  const groups = new Map<string, Spec[]>();
  for (const raw of product.value?.technical_specifications ?? []) {
    const name = toStr(raw['name']) || toStr(raw['label']) || toStr(raw['feature']);
    const value = toStr(raw['value']) || toStr(raw['presentation_value']);
    if (!name || !value) continue;
    const group = toStr(raw['group']);
    const unit = toStr(raw['unit']);
    const arr = groups.get(group) ?? [];
    arr.push({ name, value, unit });
    groups.set(group, arr);
  }
  return [...groups.entries()].map(([group, specs]) => ({ group, specs }));
});

function pickUrl(obj: unknown): string | null {
  if (typeof obj === 'string') return obj;
  if (obj && typeof obj === 'object' && 'url' in obj) {
    const u = (obj as Record<string, unknown>)['url'];
    return typeof u === 'string' ? u : null;
  }
  return null;
}

const gallery = computed<string[]>(() => {
  const urls: string[] = [];
  const main = product.value?.image_url ?? product.value?.supplier_image_url;
  if (main) urls.push(main);
  for (const raw of product.value?.icecat_images ?? []) {
    const url =
      pickUrl(raw['medium']) ??
      pickUrl(raw['low']) ??
      pickUrl(raw['high']) ??
      pickUrl(raw['thumb']) ??
      pickUrl(raw);
    if (url && !urls.includes(url)) urls.push(url);
  }
  return urls;
});

const visibleSpecGroups = computed(() =>
  showAllSpecs.value ? specGroups.value : specGroups.value.slice(0, SPEC_GROUPS_SHOWN),
);

const specCount = computed(() => specGroups.value.reduce((n, g) => n + g.specs.length, 0));

const hiddenSpecCount = computed(
  () => specCount.value - visibleSpecGroups.value.reduce((n, g) => n + g.specs.length, 0),
);

const mainImage = computed(() => selectedImage.value ?? gallery.value[0] ?? null);

const publicSiteUrl = import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? '';

const canonicalHref = computed(() => {
  if (!publicSiteUrl || !product.value) return '';
  return `${publicSiteUrl}${route.path}`;
});

useMeta(() => {
  const title = product.value ? `${product.value.name} | Natimai` : 'Produit | Natimai';
  const description =
    plainDescription.value || 'Consultez les détails et caractéristiques du produit.';
  const meta: Record<string, { name?: string; property?: string; content: string }> = {
    description: {
      name: 'description',
      content: description,
    },
    ogTitle: {
      property: 'og:title',
      content: title,
    },
    ogDescription: {
      property: 'og:description',
      content: description,
    },
    ogType: {
      property: 'og:type',
      content: 'product',
    },
  };

  const link: Record<string, { rel: string; href: string }> = {};
  if (canonicalHref.value) {
    meta['ogUrl'] = {
      property: 'og:url',
      content: canonicalHref.value,
    };
    link['canonical'] = {
      rel: 'canonical',
      href: canonicalHref.value,
    };
  }

  return {
    title,
    meta,
    link,
  };
});

async function loadProduct() {
  loading.value = true;
  error.value = null;
  selectedImage.value = null;
  cartError.value = null;
  quantity.value = 1;
  justAdded.value = false;
  showAllSpecs.value = false;
  shippingModes.value = [];
  selectedModeKey.value = null;
  offers.value = null;
  keySpecs.value = [];

  const routeId = typeof route.params.id === 'string' ? route.params.id : null;
  if (!routeId) {
    product.value = null;
    error.value = 'Produit introuvable';
    loading.value = false;
    return;
  }

  try {
    const data = await getProductById(routeId);
    product.value = data;

    // Shipping modes and sibling offers are interactive/client-only — skip on SSR
    if (typeof window !== 'undefined') {
      void loadShippingModes(routeId);
      void loadOffers(routeId);
      void loadKeySpecs(routeId);
    }

    const expectedSlug = slugifyProductName(data.name);
    const currentSlug = typeof route.params.slug === 'string' ? route.params.slug : '';
    if (expectedSlug && expectedSlug !== currentSlug) {
      void router.replace({
        ...getProductRouteByIdAndName(data.id, data.name),
        query: route.query,
      });
    }
  } catch (e) {
    product.value = null;
    const requestError = e as {
      response?: { status?: number; data?: { detail?: string; message?: string } };
      message?: string;
    };
    if (requestError.response?.status === 404) {
      error.value = 'Produit introuvable';
    } else {
      error.value =
        requestError.response?.data?.message ??
        requestError.response?.data?.detail ??
        requestError.message ??
        'Erreur inconnue';
    }
  } finally {
    loading.value = false;
  }
}

function setQuantity(value: number) {
  quantity.value = Math.max(1, Math.floor(value));
  justAdded.value = false;
}

async function onAddToCart() {
  if (!product.value) return;

  cartError.value = null;
  const ok = await cartStore.addItem(product.value.id, quantity.value, product.value);
  if (ok) {
    justAdded.value = true;
    return;
  }
  cartError.value = cartStore.error ?? "Impossible d'ajouter cet article au panier.";
}

async function loadShippingModes(productId: string): Promise<void> {
  try {
    const data = await getProductShippingModes(productId);
    shippingModes.value = data.shipping_modes;
    // Price shown for the default service level (resolved server-side, which
    // prefers the user's preferred_shipping_mode). The delivery mode is chosen
    // per order at checkout, not per product.
    selectedModeKey.value = data.default_mode;
  } catch {
    shippingModes.value = [];
    selectedModeKey.value = null;
  }
}

async function loadKeySpecs(productId: string): Promise<void> {
  try {
    keySpecs.value = (await getProductKeySpecs(productId)).specs;
  } catch {
    keySpecs.value = [];
  }
}

async function loadOffers(productId: string): Promise<void> {
  try {
    offers.value = await getProductOffers(productId);
  } catch {
    offers.value = null;
  }
}

onServerPrefetch(loadProduct);

// La barre d'achat mobile est fixe : le corps de page lui réserve sa hauteur
// pour qu'elle ne masque pas le pied de page.
onBeforeUnmount(() => {
  document.body.classList.remove('has-buy-bar');
});

onMounted(async () => {
  document.body.classList.add('has-buy-bar');
  void productsStore.loadCategories();
  await loadProduct();
});

watch(
  () => route.params.id,
  (current, previous) => {
    if (current && current !== previous) {
      void loadProduct();
    }
  },
);
</script>

<style scoped lang="scss">
.product {
  padding-top: 20px;
  padding-bottom: 96px;
}

.product__crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-bottom: 20px;
  font-size: 13px;
  color: var(--n-ink-3);

  a {
    flex-shrink: 0;
    color: inherit;
    text-decoration: none;

    &:hover {
      color: var(--n-accent);
    }
  }
}

.product__crumb-current {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--n-ink-2);
}

.product__hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 480px;
  gap: 64px;
  align-items: start;

  @media (max-width: 1279px) {
    grid-template-columns: minmax(0, 1fr) 420px;
    gap: 48px;
  }

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 28px;
  }
}

.product__skeleton-media {
  aspect-ratio: 4 / 3;
  height: auto;
  border-radius: 8px;
}

.product__gallery {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.product__thumbs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scrollbar-width: none;
}

.product__thumb {
  flex-shrink: 0;
  width: 80px;
  padding: 0;
  border: 1.5px solid transparent;
  border-radius: 9.5px;
  background: none;
  cursor: pointer;
  transition: border-color 0.2s ease;

  &:hover {
    border-color: var(--n-line-2);
  }

  &--active,
  &--active:hover {
    border-color: var(--n-ink);
  }

  @media (max-width: 767px) {
    width: 64px;
  }
}

.product__buy {
  position: sticky;
  top: 88px;
  display: flex;
  flex-direction: column;
  min-width: 0;

  @media (max-width: 1023px) {
    position: static;
  }
}

.product__brand {
  align-self: flex-start;
  font-size: 14px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.product__title {
  margin: 8px 0 0;
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;

  @media (max-width: 767px) {
    font-size: 22px;
  }
}

.product__ids {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 20px;
  font-size: 12px;
  color: var(--n-ink-3);
}

.product__price-block {
  margin-top: 28px;
  padding-top: 28px;
  border-top: 1px solid var(--n-line);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.product__price {
  font-size: 34px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.02em;
}

.product__price-note {
  font-size: 13px;
  color: var(--n-ink-3);
}

.product__stock {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--n-ink-2);

  &--order {
    color: var(--n-ink-3);
  }
}

.product__actions {
  margin-top: 24px;
  display: flex;
  gap: 8px;
}

.qty {
  flex-shrink: 0;
  height: 48px;
  display: flex;
  align-items: center;
  border: 1px solid var(--n-line-2);
  border-radius: 8px;
}

.qty__btn {
  width: 44px;
  height: 46px;
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
  font-size: 15px;
  font-weight: 500;
}

.product__add {
  flex-grow: 1;
  min-height: 48px;
  font-size: 15px;
}

.product__added {
  flex-grow: 1;
  min-height: 48px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px solid var(--n-accent);
  border-radius: 8px;
  background: var(--n-accent-soft);
  color: var(--n-accent);
  font-size: 15px;
  font-weight: 500;
  text-decoration: none;
}

.product__offers {
  margin-top: 36px;
}

.product__about {
  margin-top: 96px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 480px;
  gap: 64px;

  @media (max-width: 1279px) {
    grid-template-columns: minmax(0, 1fr) 420px;
    gap: 48px;
  }

  @media (max-width: 1023px) {
    margin-top: 56px;
    grid-template-columns: minmax(0, 1fr);
    gap: 40px;
  }
}

.product__h2 {
  margin: 0 0 16px;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.015em;
}

.product__description {
  max-width: 65ch;
  font-size: 16px;
  line-height: 1.65;
  color: var(--n-ink-2);

  :deep(p) {
    margin: 0 0 14px;
  }

  :deep(ul),
  :deep(ol) {
    margin: 0 0 14px;
    padding-left: 1.2em;
  }

  :deep(img) {
    max-width: 100%;
    height: auto;
  }
}

.product__features {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;

  li {
    display: flex;
    gap: 12px;
    font-size: 15px;
    line-height: 1.45;
  }

  .q-icon {
    flex-shrink: 0;
    margin-top: 1px;
  }
}

.product__specs {
  margin-top: 96px;
  display: flex;
  flex-direction: column;
  gap: 16px;

  @media (max-width: 1023px) {
    margin-top: 56px;
  }
}

.key-specs {
  margin: 0 0 16px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;

  @media (max-width: 1023px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.key-specs__tile {
  min-width: 0;
  padding: 24px;
  display: flex;
  flex-direction: column-reverse;
  justify-content: flex-end;
  gap: 6px;
  border-radius: 8px;
  background: var(--n-tile);

  @media (max-width: 767px) {
    padding: 16px;
  }
}

.key-specs__value {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
  overflow-wrap: anywhere;

  @media (max-width: 767px) {
    font-size: 18px;
  }
}

.key-specs__label {
  font-size: 13px;
  color: var(--n-ink-2);
}

.product__spec-groups {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 40px 48px;

  @media (max-width: 1023px) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  @media (max-width: 767px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
  }
}

.spec-group__title {
  margin: 0 0 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--n-line);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
}

.spec-group__list {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.spec-group__row {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 12px;
  font-size: 14px;
  line-height: 1.4;

  dt {
    color: var(--n-ink-3);
  }

  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
}

.product__specs-more {
  align-self: flex-start;
  min-height: 44px;
  margin-top: 16px;
}

.product__mobile-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--n-surface);
  border-top: 1px solid var(--n-line);
}

.product__mobile-price {
  flex-shrink: 0;
  font-size: 18px;
  font-weight: 600;
}
</style>
