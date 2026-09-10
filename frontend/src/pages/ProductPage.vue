<template>
  <q-page class="product-page q-pa-md">
    <q-breadcrumbs class="text-grey-7 q-mb-md">
      <q-breadcrumbs-el icon="storefront" label="Catalogue" :to="{ name: 'catalogue' }" />
      <q-breadcrumbs-el :label="product?.name ?? 'Produit'" />
    </q-breadcrumbs>

    <div v-if="loading" class="row q-col-gutter-md">
      <div class="col-12 col-md-5">
        <q-skeleton height="420px" square />
      </div>
      <div class="col-12 col-md-7">
        <q-skeleton type="text" width="70%" />
        <q-skeleton type="text" width="40%" class="q-mt-sm" />
        <q-skeleton type="text" width="20%" class="q-mt-lg" />
        <q-skeleton type="text" width="95%" class="q-mt-md" />
        <q-skeleton type="text" width="85%" />
      </div>
    </div>

    <q-banner v-else-if="error" class="bg-red-1 text-red-8" rounded>
      <template #avatar><q-icon name="error_outline" /></template>
      {{ error }}
      <template #action>
        <q-btn flat color="primary" label="Retour au catalogue" :to="{ name: 'catalogue' }" />
      </template>
    </q-banner>

    <q-card v-else-if="product" class="product-page-card" flat bordered>
      <q-card-section class="row q-col-gutter-lg">
        <div class="col-12 col-md-5">
          <q-img
            :src="mainImage ?? placeholderImg"
            :ratio="1"
            fit="contain"
            class="rounded-borders bg-grey-1"
          >
            <template #error>
              <div class="absolute-full flex flex-center bg-grey-2">
                <q-icon name="image_not_supported" size="3rem" color="grey-5" />
              </div>
            </template>
          </q-img>

          <div v-if="gallery.length > 1" class="row q-gutter-xs q-mt-sm">
            <q-img
              v-for="(url, i) in gallery"
              :key="i"
              :src="url"
              :ratio="1"
              width="68px"
              fit="contain"
              class="cursor-pointer rounded-borders bg-grey-1 gallery-thumb"
              :class="{ 'gallery-thumb--active': url === mainImage }"
              @click="selectedImage = url"
            />
          </div>
        </div>

        <div class="col-12 col-md-7">
          <h1 class="text-h5 text-weight-bold q-my-none">{{ product.name }}</h1>

          <div class="text-caption text-grey-6 q-mt-sm">
            {{ product.manufacturer ?? product.supplier_name ?? '—' }}
          </div>
          <div v-if="product.vendor_part_number" class="text-caption text-grey-5">
            Réf. {{ product.vendor_part_number }}
          </div>
          <div v-if="product.ean" class="text-caption text-grey-5">EAN {{ product.ean }}</div>

          <div class="text-h4 text-weight-bold text-primary q-mt-md">
            {{ displayPrice }}
          </div>
          <div
            v-if="!selectedMode && product.base_price === '0.00'"
            class="text-caption text-grey-6"
          >
            Prix sur devis
          </div>

          <div v-if="hasVariants && variants" class="q-mt-md" data-testid="variant-selectors">
            <div v-for="axis in variants.axes" :key="axis" class="q-mb-sm">
              <div class="text-caption text-grey-7 q-mb-xs">{{ axis }}</div>
              <div class="row q-gutter-xs">
                <q-btn
                  v-for="value in optionValues[axis] ?? []"
                  :key="value"
                  dense
                  no-caps
                  :outline="selectedOptions[axis] !== value"
                  :unelevated="selectedOptions[axis] === value"
                  color="primary"
                  :label="value"
                  :class="{ 'variant-unavailable': !isValueAvailable(axis, value) }"
                  @click="selectOption(axis, value)"
                />
              </div>
            </div>
            <div v-if="selectedVariant" class="text-caption text-grey-6">
              {{ selectedVariant.name }}
              <span v-if="selectedVariant.supplier_sku">
                — réf. {{ selectedVariant.supplier_sku }}</span
              >
            </div>
            <div v-else class="text-caption text-grey-6">
              Choisissez une déclinaison pour voir son prix et sa disponibilité.
            </div>
          </div>

          <div
            v-if="!needsVariantChoice"
            class="text-body2 q-mt-sm"
            :class="isOutOfStock ? 'text-grey-6' : 'text-positive'"
          >
            <q-icon name="inventory_2" size="16px" class="q-mr-xs" />
            <span v-if="isOutOfStock">Sur commande</span>
            <span v-else>{{ stockQuantity }} en stock</span>
          </div>

          <div v-if="product.parent_product_id" class="text-caption q-mt-sm">
            <router-link :to="getProductRouteByIdAndName(product.parent_product_id, product.name)">
              Voir toutes les déclinaisons
            </router-link>
          </div>

          <div
            v-if="safeDescription"
            class="text-body1 q-mt-md product-description"
            v-html="safeDescription"
          ></div>

          <ProductOffers :offers="offers" class="q-mt-md" />
        </div>
      </q-card-section>

      <q-card-section v-if="features.length > 0" class="q-pt-none">
        <div class="text-subtitle2 q-mb-xs">Points clés</div>
        <ul class="q-pl-md q-my-none">
          <li v-for="(feat, i) in features" :key="i" class="text-body2">{{ feat }}</li>
        </ul>
      </q-card-section>

      <q-card-section v-if="specGroups.length > 0" class="q-pt-none">
        <div class="text-subtitle2 q-mb-sm">Caractéristiques techniques</div>
        <div v-for="grp in specGroups" :key="grp.group" class="q-mb-md">
          <div v-if="grp.group" class="text-caption text-grey-7 q-mb-xs">
            {{ grp.group }}
          </div>
          <q-markup-table flat dense bordered wrap-cells>
            <tbody>
              <tr v-for="(spec, i) in grp.specs" :key="i">
                <td class="text-grey-8" style="width: 45%">{{ spec.name }}</td>
                <td>{{ spec.value }}{{ spec.unit ? ' ' + spec.unit : '' }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn flat label="Retour au catalogue" color="grey-7" :to="{ name: 'catalogue' }" />
        <q-btn
          unelevated
          color="primary"
          icon="add_shopping_cart"
          label="Ajouter au panier"
          :disable="needsVariantChoice || isOutOfStock"
          @click="onAddToCart"
        />
      </q-card-actions>

      <q-banner
        v-if="cartFeedback"
        :class="cartFeedback.ok ? 'bg-green-1 text-green-9' : 'bg-orange-1 text-orange-10'"
        class="q-mx-lg q-mb-lg"
        rounded
      >
        <template #avatar>
          <q-icon :name="cartFeedback.ok ? 'check_circle' : 'warning_amber'" />
        </template>
        {{ cartFeedback.message }}
      </q-banner>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import DOMPurify from 'isomorphic-dompurify';
import { useMeta } from 'quasar';
import { computed, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { components } from '@app/api-types';
import {
  getProductById,
  getProductOffers,
  getProductShippingModes,
  getProductVariants,
  type ProductOffersResponse,
  type ProductVariantsResponse,
  type ShippingModePricePublic,
  sellableQuantity,
  trackProductView,
} from 'src/api/products';
import ProductOffers from 'src/components/ProductOffers.vue';
import { useCartStore } from 'src/stores/cart';
import { useCurrencyStore } from 'src/stores/currency';
import { getProductRouteByIdAndName, slugifyProductName } from 'src/utils/productRoute';

type ProductPublic = components['schemas']['ProductPublic'];
type Spec = { name: string; value: string; unit: string };

const route = useRoute();
const router = useRouter();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();

const placeholderImg = '/icons/placeholder-product.svg';
const product = ref<ProductPublic | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const cartFeedback = ref<{ ok: boolean; message: string } | null>(null);
const selectedImage = ref<string | null>(null);

const shippingModes = ref<ShippingModePricePublic[]>([]);
const selectedModeKey = ref<string | null>(null);
const offers = ref<ProductOffersResponse | null>(null);

// Variants: the page opens on the parent; the customer picks option values
// and the matching variant (a product of its own) is what gets priced,
// stocked and added to the cart.
const variants = ref<ProductVariantsResponse | null>(null);
const selectedOptions = ref<Record<string, string>>({});
const hasVariants = computed(() => Boolean(product.value?.has_variants));

const optionValues = computed<Record<string, string[]>>(() => {
  const out: Record<string, string[]> = {};
  for (const axis of variants.value?.axes ?? []) {
    const values: string[] = [];
    for (const v of variants.value?.variants ?? []) {
      const value = v.variant_options?.[axis];
      if (value && !values.includes(value)) values.push(value);
    }
    out[axis] = values;
  }
  return out;
});

const selectedVariant = computed<ProductPublic | null>(() => {
  const list = variants.value?.variants ?? [];
  const axes = variants.value?.axes ?? [];
  if (!list.length || axes.some((axis) => !selectedOptions.value[axis])) return null;
  return (
    list.find((v) =>
      axes.every((axis) => v.variant_options?.[axis] === selectedOptions.value[axis]),
    ) ?? null
  );
});

/** Whether a value is still reachable given the other axes already chosen. */
function isValueAvailable(axis: string, value: string): boolean {
  const list = variants.value?.variants ?? [];
  return list.some((v) => {
    if (v.variant_options?.[axis] !== value) return false;
    for (const [other, chosen] of Object.entries(selectedOptions.value)) {
      if (other !== axis && chosen && v.variant_options?.[other] !== chosen) return false;
    }
    return sellableQuantity(v) > 0;
  });
}

function selectOption(axis: string, value: string) {
  selectedOptions.value = { ...selectedOptions.value, [axis]: value };
}

/** The product actually shown / sold: the chosen variant, else the page's product. */
const effectiveProduct = computed<ProductPublic | null>(
  () => selectedVariant.value ?? product.value,
);

const stockQuantity = computed(() =>
  effectiveProduct.value ? sellableQuantity(effectiveProduct.value) : 0,
);
const isOutOfStock = computed(() => stockQuantity.value <= 0);
const needsVariantChoice = computed(() => hasVariants.value && !selectedVariant.value);

const selectedMode = computed(
  () => shippingModes.value.find((m) => m.service_level === selectedModeKey.value) ?? null,
);

const displayPrice = computed(() => {
  if (selectedMode.value) {
    const price = parseFloat(selectedMode.value.sale_price);
    return price > 0 ? currencyStore.format(price) : '—';
  }
  if (!effectiveProduct.value) return '—';
  const price = parseFloat(effectiveProduct.value.base_price);
  if (price === 0) return '—';
  const formatted = currencyStore.format(price);
  return needsVariantChoice.value ? `À partir de ${formatted}` : formatted;
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
  const variantImage = selectedVariant.value?.image_url ?? null;
  if (variantImage) urls.push(variantImage);
  const main = product.value?.image_url ?? product.value?.supplier_image_url;
  if (main && !urls.includes(main)) urls.push(main);
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
  shippingModes.value = [];
  selectedModeKey.value = null;
  offers.value = null;

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
    variants.value = null;
    selectedOptions.value = {};
    if (data.has_variants) {
      try {
        variants.value = await getProductVariants(routeId);
        // One variant only: nothing to choose, select it.
        if (variants.value.variants.length === 1) {
          selectedOptions.value = { ...(variants.value.variants[0]?.variant_options ?? {}) };
        }
      } catch {
        variants.value = null;
      }
    }

    // Shipping modes and sibling offers are interactive/client-only — skip on SSR
    if (typeof window !== 'undefined') {
      void loadShippingModes(routeId);
      void loadOffers(routeId);
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

async function onAddToCart() {
  const target = effectiveProduct.value;
  if (!target) return;
  if (needsVariantChoice.value) {
    cartFeedback.value = { ok: false, message: 'Choisissez une déclinaison.' };
    return;
  }

  cartFeedback.value = null;
  const ok = await cartStore.addItem(target.id, 1, target);
  if (ok) {
    cartFeedback.value = {
      ok: true,
      message: `${target.name} ajouté au panier.`,
    };
    return;
  }

  cartFeedback.value = {
    ok: false,
    message: cartStore.error ?? "Impossible d'ajouter cet article au panier.",
  };
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

async function loadOffers(productId: string): Promise<void> {
  try {
    offers.value = await getProductOffers(productId);
  } catch {
    offers.value = null;
  }
}

onServerPrefetch(loadProduct);

onMounted(async () => {
  await loadProduct();
  // Client only: the SSR pass must not count a view, and a bot-heavy server
  // render would skew the « plus consultés » ranking.
  if (process.env.CLIENT && product.value) void trackProductView(product.value.id);
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

<style scoped>
.variant-unavailable {
  opacity: 0.45;
}
</style>

<style scoped lang="scss">
.product-page {
  max-width: 1200px;
  margin: 0 auto;
}

.product-page-card {
  overflow: hidden;
}

.gallery-thumb {
  border: 1px solid transparent;

  &--active {
    border-color: var(--q-primary);
  }
}

.product-description {
  :deep(p) {
    margin: 0 0 0.5em;
  }

  :deep(ul),
  :deep(ol) {
    margin: 0 0 0.5em;
    padding-left: 1.2em;
  }

  :deep(img) {
    max-width: 100%;
    height: auto;
  }
}
</style>
