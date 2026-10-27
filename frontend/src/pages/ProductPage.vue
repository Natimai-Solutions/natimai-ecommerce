<template>
  <q-page class="product page-container">
    <nav class="product__crumbs" :aria-label="$t('product.crumbs')">
      <router-link :to="{ name: 'catalogue' }">{{ $t('layout.catalogue') }}</router-link>
      <template v-for="crumb in categoryCrumbs" :key="crumb.id">
        <q-icon name="ph:caret-right" size="12px" />
        <router-link :to="{ name: 'catalogue', query: { cat: crumb.id } }">
          {{ crumb.label }}
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
        <q-btn flat :label="$t('product.back_to_catalogue')" :to="{ name: 'catalogue' }" />
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
          <div
            v-if="gallery.length > 1"
            class="product__thumbs"
            role="list"
            :aria-label="$t('product.photos')"
          >
            <button
              v-for="(url, i) in gallery"
              :key="url"
              type="button"
              role="listitem"
              class="product__thumb"
              :class="{ 'product__thumb--active': url === mainImage }"
              :aria-label="$t('product.photo_n', { n: i + 1 })"
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
          <span
            v-if="isRefurbished(product)"
            class="product__refurb-badge"
            data-testid="product-condition-badge"
          >
            <q-icon name="ph:arrows-counter-clockwise" size="14px" />
            {{ conditionLabel(product, tr) }}
          </span>
          <h1 class="product__title">{{ product.name }}</h1>
          <p v-if="shortDescription" class="product__lead" data-testid="product-lead">
            {{ shortDescription }}
          </p>
          <div v-if="product.vendor_part_number || product.ean" class="product__ids font-mono">
            <span v-if="product.vendor_part_number">{{
              $t('product.ref', { ref: product.vendor_part_number })
            }}</span>
            <span v-if="product.ean">EAN {{ product.ean }}</span>
          </div>

          <div class="product__price-block">
            <span v-if="needsVariantChoice && !isQuote" class="product__price-note">
              {{ $t('product.from') }}
            </span>
            <span v-if="isQuote" class="product__price">{{ $t('product.on_quote') }}</span>
            <span v-else class="product__price">
              <span class="font-mono" :class="{ 'product__promo-price': regularPrice }">{{
                displayPrice
              }}</span>
              <span class="product__tax" data-testid="product-price-tax">{{
                $t('product.incl_tax')
              }}</span>
            </span>
            <span
              v-if="regularPrice && !isQuote"
              class="product__promo"
              data-testid="product-promo"
            >
              <s class="font-mono">{{ regularPrice }}</s>
              <span class="product__promo-badge">{{ promoLabel }}</span>
              <span v-if="promotionEnds" class="product__price-note">
                {{ $t('product.promo_until', { date: promotionEnds }) }}
              </span>
            </span>
            <span v-if="selectedMode?.customer_label" class="product__price-note">
              {{ $t('product.mode_price', { mode: selectedMode.customer_label.toLowerCase() }) }}
            </span>
            <span
              v-if="!needsVariantChoice"
              class="product__stock"
              :class="{ 'product__stock--order': availability.preorder || isOutOfStock }"
            >
              <span
                class="stock-dot"
                :class="{
                  'stock-dot--order': availability.preorder || isOutOfStock,
                  'stock-dot--supplier': availability.source === 'supplier',
                }"
                aria-hidden="true"
              /><span data-testid="product-stock" :data-source="availability.source">{{
                availability.label
              }}</span>
            </span>
            <span
              v-if="!needsVariantChoice && availability.note"
              class="product__price-note"
              data-testid="product-stock-note"
            >
              {{ availability.note }}
            </span>
            <router-link
              v-if="product.parent_product_id"
              :to="getProductRouteByIdAndName(product.parent_product_id, product.name)"
              class="product__variants-link"
            >
              {{ $t('product.all_variants') }}
            </router-link>
          </div>

          <div
            v-if="departureStore.next && availability.source !== 'local'"
            class="product__departure"
            data-testid="product-departure"
          >
            <q-icon name="ph:calendar-check" size="18px" />
            <span>
              {{ $t('product.departure', { name: departureStore.next.name, cutoff: nextCutoff }) }}
              <template v-if="nextDelivery"> {{ nextDelivery }}. </template>
            </span>
          </div>

          <!-- État et détails du reconditionné dans une seule grille : mêmes
               colonnes, et le grade (déjà dans « État ») n'est pas répété. -->
          <dl class="product__refurb">
            <div class="spec-group__row">
              <dt>{{ $t('product.condition') }}</dt>
              <dd data-testid="product-condition">{{ conditionLabel(product, tr) }}</dd>
            </div>
            <div v-for="d in refurbDetails" :key="d.label" class="spec-group__row">
              <dt>{{ d.label }}</dt>
              <dd>{{ d.value }}</dd>
            </div>
          </dl>

          <div v-if="hasVariants && variants" class="variants" data-testid="variant-selectors">
            <div v-for="axis in variants.axes" :key="axis" class="variants__axis">
              <span :id="`axis-${axis}`" class="variants__label">{{ axis }}</span>
              <div class="variants__options" role="group" :aria-labelledby="`axis-${axis}`">
                <!-- Déclinaisons optionnelles : « Standard » = le produit de
                     base, tel que décrit sur la fiche ; une valeur le remplace. -->
                <button
                  v-if="variantsOptional"
                  type="button"
                  class="variants__option"
                  :class="{ 'variants__option--active': !selectedOptions[axis] }"
                  :aria-pressed="!selectedOptions[axis]"
                  data-testid="variant-base"
                  @click="clearOption(axis)"
                >
                  {{ $t('product.variant_base') }}
                </button>
                <button
                  v-for="value in optionValues[axis] ?? []"
                  :key="value"
                  type="button"
                  class="variants__option"
                  :class="{
                    'variants__option--active': selectedOptions[axis] === value,
                    'variants__option--unavailable': !isValueAvailable(axis, value),
                  }"
                  :aria-pressed="selectedOptions[axis] === value"
                  @click="selectOption(axis, value)"
                >
                  {{ value }}
                  <span
                    v-if="optionExtra(axis, value)"
                    class="variants__extra font-mono"
                    data-testid="variant-extra"
                    >{{ optionExtra(axis, value) }}</span
                  >
                </button>
              </div>
            </div>
            <p v-if="selectedVariant?.supplier_sku" class="variants__hint font-mono">
              {{ $t('product.ref', { ref: selectedVariant.supplier_sku }) }}
            </p>
            <p v-else-if="!variantsOptional && !selectedVariant" class="variants__hint">
              {{ $t('product.choose_variant_hint') }}
            </p>
            <p v-else-if="partialSelection" class="variants__hint">
              {{ $t('product.variant_combo_missing') }}
            </p>
            <p v-else-if="!selectedVariant" class="variants__hint">
              {{ $t('product.variant_base_hint') }}
            </p>
          </div>

          <div class="product__actions">
            <div class="qty" role="group" :aria-label="$t('product.quantity')">
              <button
                type="button"
                class="qty__btn"
                :aria-label="$t('product.qty_less')"
                :disabled="quantity <= 1"
                @click="setQuantity(quantity - 1)"
              >
                <q-icon name="ph:minus" size="16px" />
              </button>
              <span class="qty__value font-mono" aria-live="polite">{{ quantity }}</span>
              <button
                type="button"
                class="qty__btn"
                :aria-label="$t('product.qty_more')"
                @click="setQuantity(quantity + 1)"
              >
                <q-icon name="ph:plus" size="16px" />
              </button>
            </div>

            <router-link v-if="justAdded" :to="{ name: 'cart' }" class="product__added">
              <q-icon name="ph:check-circle" size="20px" />
              {{ $t('product.added_view_cart') }}
            </router-link>
            <q-btn
              v-else-if="isOutOfStock && !needsVariantChoice"
              outline
              color="primary"
              icon="ph:bell"
              :label="$t('product.notify_me')"
              class="product__add"
              data-testid="product-notify-me"
              @click="openAlert"
            />
            <q-btn
              v-else
              unelevated
              color="primary"
              icon="ph:shopping-bag"
              :label="$t('product.add_to_cart')"
              class="product__add"
              data-testid="product-page-add-to-cart"
              :disable="needsVariantChoice || isOutOfStock"
              :loading="cartStore.mutating"
              @click="onAddToCart"
            />
            <q-btn
              outline
              color="primary"
              icon="ph:heart"
              class="product__wish"
              :class="{ 'product__wish--on': inWishlist }"
              :aria-pressed="inWishlist"
              :aria-label="inWishlist ? $t('product.wish_remove') : $t('product.wish_add')"
              :loading="wishSaving"
              data-testid="product-wishlist"
              @click="toggleWishlist"
            >
              <q-tooltip>{{
                inWishlist ? $t('product.wish_in') : $t('product.wish_add')
              }}</q-tooltip>
            </q-btn>
            <q-btn
              outline
              color="primary"
              icon="ph:scales"
              class="product__wish"
              :class="{ 'product__wish--on': inCompare }"
              :aria-pressed="inCompare"
              :aria-label="
                inCompare
                  ? $t('compare.remove', { name: product.name })
                  : $t('compare.add', { name: product.name })
              "
              data-testid="product-compare"
              @click="toggleCompare"
            >
              <q-tooltip>{{
                inCompare ? $t('compare.remove_short') : $t('compare.add_short')
              }}</q-tooltip>
            </q-btn>
          </div>

          <AppNotice v-if="cartError" tone="warning" dense class="q-mt-md">
            {{ cartError }}
          </AppNotice>
          <AppNotice v-if="alertNotice" tone="success" dense class="q-mt-md">
            {{ alertNotice }}
          </AppNotice>

          <ProductOffers :offers="offers" class="product__offers" />
        </div>
      </section>

      <section v-if="safeDescription || features.length > 0" class="product__about">
        <div v-if="safeDescription">
          <h2 class="product__h2">{{ $t('product.description') }}</h2>
          <!-- eslint-disable-next-line vue/no-v-html -- nettoyé par DOMPurify -->
          <div class="product__description" v-html="safeDescription"></div>
        </div>
        <div v-if="features.length > 0">
          <h2 class="product__h2">{{ $t('product.key_points') }}</h2>
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
        <h2 id="specs-title" class="product__h2">{{ $t('product.specs') }}</h2>
        <dl v-if="showKeySpecs" class="key-specs">
          <div v-for="spec in keySpecs" :key="spec.key" class="key-specs__tile">
            <dt class="key-specs__label">{{ spec.label }}</dt>
            <dd class="key-specs__value tabular-nums">{{ spec.value }}</dd>
          </div>
        </dl>
        <div class="product__spec-groups">
          <div v-for="grp in visibleSpecGroups" :key="grp.group" class="spec-group">
            <h3 class="spec-group__title">{{ grp.group || $t('product.specs_general') }}</h3>
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
          :label="$t('product.specs_all', { n: specCount })"
          class="product__specs-more"
          @click="showAllSpecs = true"
        />
      </section>

      <ProductReviews :product-id="product.id" class="product__reviews" />

      <section
        v-if="related.accessories.length > 0"
        class="product__related"
        aria-labelledby="related-title"
        data-testid="product-related"
      >
        <h2 id="related-title" class="product__h2">{{ $t('product.complete_setup') }}</h2>
        <div class="product-grid">
          <ProductCard
            v-for="item in related.accessories"
            :key="item.id"
            :product="item"
            @add-to-cart="addRelatedToCart"
          />
        </div>
      </section>
      <section
        v-if="related.alternatives.length > 0"
        class="product__related"
        aria-labelledby="alternatives-title"
        data-testid="product-alternatives"
      >
        <h2 id="alternatives-title" class="product__h2">{{ $t('product.alternatives') }}</h2>
        <div class="product-grid">
          <ProductCard
            v-for="item in related.alternatives"
            :key="item.id"
            :product="item"
            @add-to-cart="addRelatedToCart"
          />
        </div>
      </section>

      <!-- Barre d'achat mobile, toujours à portée de pouce -->
      <div class="lt-md product__mobile-bar">
        <div class="product__mobile-price">
          <span v-if="needsVariantChoice && !isQuote" class="product__price-note">{{
            $t('product.from')
          }}</span>
          <span v-if="isQuote">{{ $t('product.on_quote') }}</span>
          <span v-else class="font-mono">{{ displayPrice }}</span>
        </div>
        <router-link v-if="justAdded" :to="{ name: 'cart' }" class="product__added">
          <q-icon name="ph:check-circle" size="20px" />
          {{ $t('product.view_cart') }}
        </router-link>
        <q-btn
          v-else-if="isOutOfStock && !needsVariantChoice"
          outline
          color="primary"
          :label="$t('product.notify_me')"
          class="product__add"
          @click="openAlert"
        />
        <q-btn
          v-else
          unelevated
          color="primary"
          :label="$t('product.add_short')"
          class="product__add"
          :disable="needsVariantChoice || isOutOfStock"
          :loading="cartStore.mutating"
          @click="onAddToCart"
        />
      </div>

      <!-- « Me prévenir » : un e-mail quand l'article redevient commandable -->
      <q-dialog v-model="alertDialog">
        <q-card flat class="alert-dialog">
          <q-form @submit.prevent="submitAlert">
            <q-card-section>
              <h2 class="alert-dialog__title">{{ $t('product.alert_title') }}</h2>
              <p class="alert-dialog__text">
                {{ $t('product.alert_text', { name: product.name }) }}
              </p>
              <q-input
                v-model="alertEmail"
                type="email"
                :label="$t('product.alert_email')"
                outlined
                stack-label
                autofocus
                autocomplete="email"
                :hint="authStore.isAuthenticated ? $t('product.alert_email_hint') : undefined"
                :rules="[
                  (v: string) =>
                    (authStore.isAuthenticated && !v) ||
                    /.+@.+\..+/.test(v) ||
                    $t('product.invalid_email'),
                ]"
              />
              <div
                v-if="captcha.enabled.value && !authStore.isAuthenticated"
                ref="captchaEl"
                class="q-mt-md"
              />
              <AppNotice v-if="alertError" tone="error" dense class="q-mt-sm">
                {{ alertError }}
              </AppNotice>
            </q-card-section>
            <q-card-actions align="right" class="q-px-md q-pb-md">
              <q-btn v-close-popup flat :label="$t('common.cancel')" />
              <q-btn
                type="submit"
                unelevated
                color="primary"
                :label="$t('product.notify_me')"
                :loading="alertSaving"
                :disable="!authStore.isAuthenticated && !captcha.ready.value"
              />
            </q-card-actions>
          </q-form>
        </q-card>
      </q-dialog>
    </template>
  </q-page>
</template>
<script setup lang="ts">
import AppNotice from '@app/ui/AppNotice.vue';
import DOMPurify from 'isomorphic-dompurify';
import { useMeta } from 'quasar';
import { computed, onBeforeUnmount, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { components } from '@app/api-types';
import {
  getProductKeySpecs,
  getProductOffers,
  getProductShippingModes,
  type ProductKeySpec,
  type ProductOffersResponse,
  type ShippingModePricePublic,
  sellableQuantity,
  trackProductView,
} from '@/api/products';
import ProductImage from '@/components/ProductImage.vue';
import ProductOffers from '@/components/ProductOffers.vue';
import ProductReviews from '@/components/ProductReviews.vue';
import { useAuthStore } from '@/stores/auth';
import { addToMyWishlist, getMyWishlist, removeFromMyWishlist } from '@/api/wishlist';
import { useCartStore } from '@/stores/cart';
import { useUiStore } from '@/stores/ui';
import ProductCard from '@/components/ProductCard.vue';
import { getRelatedProducts, type RelatedProductsResponse } from '@/api/products';
import { useProductsStore } from '@/stores/products';
import { COMPARE_MAX, useCompareStore } from '@/stores/compare';
import { useCurrencyStore } from '@/stores/currency';
import { useDepartureStore } from '@/stores/departure';
import { subscribeStockAlert } from '@/api/stockAlerts';
import {
  conditionLabel,
  isRefurbished,
  productAvailability,
  refurbishedDetails,
} from '@/utils/availability';
import { useI18n } from 'vue-i18n';
import { formatDate } from '@app/utils';
import { useDepartureLabels } from '@/composables/useDepartureLabels';
import { useTranslate } from '@/composables/useTranslate';
import { useTurnstile } from '@/composables/useTurnstile';
import { absoluteUrl, breadcrumbList, jsonLd } from '@/utils/seo';
import { categoryLineage } from '@/utils/categories';
import { useShopModulesStore } from '@/stores/shopModules';
import { useProductDetailStore } from '@/stores/productDetail';
import { storeToRefs } from 'pinia';
import { getProductRouteByIdAndName, slugifyProductName } from '@/utils/productRoute';

type ProductPublic = components['schemas']['ProductPublic'];
type Spec = { name: string; value: string; unit: string };

const route = useRoute();
const router = useRouter();
const cartStore = useCartStore();
const uiStore = useUiStore();
const currencyStore = useCurrencyStore();
const productsStore = useProductsStore();

/** Groupes de caractéristiques affichés avant « Afficher toutes ». */
const SPEC_GROUPS_SHOWN = 3;

const departureStore = useDepartureStore();
const { t, locale } = useI18n({ useScope: 'global' });
const tr = useTranslate();
const shopModules = useShopModulesStore();
const { nextCutoff, nextDelivery } = useDepartureLabels();

// Product, variants and load state come from the store: the server render
// hands them to the browser (no second fetch, no hydration mismatch).
const productDetail = useProductDetailStore();
const { product, variants } = storeToRefs(productDetail);
// The store may still hold the previous product (client navigation from one
// fiche to another): loading until it holds this route's one.
const loading = computed(
  () => productDetail.loading || (!productDetail.error && product.value?.id !== route.params.id),
);
const error = computed(() => {
  const raw = productDetail.error;
  if (!raw) return null;
  if (raw === 'not_found') return t('product.not_found');
  return raw === 'unknown' ? t('product.unknown_error') : raw;
});
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

// Variants: the page opens on the parent; the customer picks option values
// and the matching variant (a product of its own) is what gets priced,
// stocked and added to the cart.
const selectedOptions = ref<Record<string, string>>({});
const hasVariants = computed(() => Boolean(product.value?.has_variants));
// Optional variants: the page's product is the base configuration, sold as
// is; picking a value replaces it, picking it again (or « Standard ») goes
// back to the base product.
const variantsOptional = computed(() => Boolean(product.value?.variants_optional));

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

const availability = computed(() =>
  productAvailability(effectiveProduct.value ?? { supplier_quantity: 0 }, tr),
);

// « Me prévenir » : an e-mail when the product is orderable again.
const authStore = useAuthStore();

// Favoris : la liste du compte (Mon compte → Favoris et alertes).
const inWishlist = ref(false);
// Comparison shortlist (R8 / confort).
const compareStore = useCompareStore();
const inCompare = computed(() => !!product.value && compareStore.has(product.value.id));
function toggleCompare() {
  if (!product.value) return;
  if (!compareStore.toggle(product.value.id)) {
    cartError.value = t('compare.full', { max: COMPARE_MAX });
  }
}
const wishSaving = ref(false);

async function refreshWishlistState() {
  if (!authStore.isAuthenticated || !product.value) return;
  try {
    const wishlist = await getMyWishlist();
    inWishlist.value = wishlist.items.some((item) => item.product_id === product.value?.id);
  } catch {
    inWishlist.value = false;
  }
}

async function toggleWishlist() {
  if (!product.value) return;
  if (!authStore.isAuthenticated) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } });
    return;
  }
  wishSaving.value = true;
  try {
    if (inWishlist.value) await removeFromMyWishlist(product.value.id);
    else await addToMyWishlist(product.value.id);
    inWishlist.value = !inWishlist.value;
  } catch (err) {
    cartError.value = extractApiMessage(err) ?? t('product.wish_failed');
  } finally {
    wishSaving.value = false;
  }
}
const alertDialog = ref(false);
const alertEmail = ref('');
// A visitor's alert goes through the captcha when the shop has one (R8 / U5);
// the dialog mounts the widget each time it opens.
const captcha = useTurnstile();
const captchaEl = ref<HTMLElement | null>(null);
watch(captchaEl, (el) => void captcha.mount(el, locale.value));
const alertSaving = ref(false);
const alertError = ref<string | null>(null);
const alertNotice = ref<string | null>(null);

function openAlert() {
  // Signed in: the account's e-mail is used server-side unless another is typed.
  alertEmail.value = '';
  alertError.value = null;
  alertDialog.value = true;
}

async function submitAlert() {
  if (!product.value) return;
  alertSaving.value = true;
  alertError.value = null;
  try {
    const alert = await subscribeStockAlert(
      product.value.id,
      alertEmail.value.trim() || null,
      captcha.headers(),
    );
    captcha.reset(); // a Turnstile token is single-use
    alertDialog.value = false;
    alertNotice.value = t('product.alert_ok', { email: alert.email });
    if (!authStore.isAuthenticated) void cartStore.attachGuestEmail(alert.email);
  } catch (err) {
    alertError.value = extractApiMessage(err) ?? t('product.alert_failed');
  } finally {
    alertSaving.value = false;
  }
}

function extractApiMessage(err: unknown): string | null {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
    }
  }
  return null;
}
const refurbDetails = computed(() =>
  product.value
    ? refurbishedDetails(product.value, tr).filter((d) => d.label !== tr('condition.grade'))
    : [],
);

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

/**
 * « + 10 000 F » next to an option whose variant carries a supplement over the
 * parent's price (R9 / T6). The variant considered is the one this value would
 * select given the other axes already chosen.
 */
function optionExtra(axis: string, value: string): string | null {
  const list = variants.value?.variants ?? [];
  const candidate = list.find((v) => {
    if (v.variant_options?.[axis] !== value) return false;
    for (const [other, chosen] of Object.entries(selectedOptions.value)) {
      if (other !== axis && chosen && v.variant_options?.[other] !== chosen) return false;
    }
    return true;
  });
  const extra = candidate?.price_extra == null ? null : Number(candidate.price_extra);
  if (extra === null || !Number.isFinite(extra) || extra <= 0) return null;
  return `+ ${currencyStore.format(extra)}`;
}

function selectOption(axis: string, value: string) {
  // A second click on the chosen value deselects it.
  if (selectedOptions.value[axis] === value) {
    clearOption(axis);
    return;
  }
  selectedOptions.value = { ...selectedOptions.value, [axis]: value };
  justAdded.value = false;
  selectedImage.value = null;
}

function clearOption(axis: string) {
  const next = { ...selectedOptions.value };
  delete next[axis];
  selectedOptions.value = next;
  justAdded.value = false;
  selectedImage.value = null;
}

/** Some axes chosen, but no variant carries that combination. */
const partialSelection = computed(
  () =>
    hasVariants.value &&
    !selectedVariant.value &&
    Object.values(selectedOptions.value).some(Boolean),
);

/** The product actually shown / sold: the chosen variant, else the page's product. */
const effectiveProduct = computed<ProductPublic | null>(
  () => selectedVariant.value ?? product.value,
);

const isOutOfStock = computed(() => !availability.value.orderable);
// Add-to-cart blocked: a variant must be chosen, or the chosen combination
// does not exist. With optional variants, nothing chosen = the base product.
const needsVariantChoice = computed(
  () =>
    hasVariants.value &&
    !selectedVariant.value &&
    (!variantsOptional.value || partialSelection.value),
);

const selectedMode = computed(
  () => shippingModes.value.find((m) => m.service_level === selectedModeKey.value) ?? null,
);

const priceValue = computed(() => {
  if (selectedMode.value) return parseFloat(selectedMode.value.sale_price);
  return effectiveProduct.value ? parseFloat(effectiveProduct.value.base_price) : 0;
});

/** Prix nul : l'article est vendu sur devis. */
const isQuote = computed(() => !(priceValue.value > 0));

// Tant qu'aucune déclinaison n'est choisie, le parent affiche la moins chère,
// précédée de « À partir de ».
const displayPrice = computed(() => currencyStore.format(priceValue.value));

// Promotion (règle du meilleur prix) : le prix habituel du client, barré.
const regularValue = computed(() => {
  const raw = selectedMode.value
    ? selectedMode.value.regular_price
    : effectiveProduct.value?.regular_price;
  const value = raw ? parseFloat(raw) : 0;
  return value > priceValue.value ? value : null;
});
const regularPrice = computed(() =>
  regularValue.value !== null ? currencyStore.format(regularValue.value) : null,
);
const promoLabel = computed(() => {
  const name = effectiveProduct.value?.promotion_name;
  const pct =
    regularValue.value !== null ? Math.round((1 - priceValue.value / regularValue.value) * 100) : 0;
  const off = pct > 0 ? `−${pct} %` : t('product.promo');
  return name ? `${off} · ${name}` : off;
});
const promotionEnds = computed(() => {
  const raw = effectiveProduct.value?.promotion_ends_at;
  return raw ? formatDate(raw) : null;
});

// « Catalogue › Réseau › WiFi › Point d'accès » : the category's lineage.
const categoryCrumbs = computed(() =>
  categoryLineage(productsStore.categories, product.value?.category_id ?? null).map((c) => ({
    id: c.id,
    label: c.title ?? c.name,
  })),
);
const categoryLabel = computed(() => {
  const chain = categoryCrumbs.value;
  return chain.length ? (chain[chain.length - 1]?.label ?? null) : null;
});

/** HTML → one line of text. */
function plainText(html: string): string {
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * The short description (admin: « Description courte ») is the lead under the
 * title and the meta description; the long one is the « Description » section.
 * Without a long description the short one is shown there instead, not twice.
 */
const shortDescription = computed(() => {
  const raw = product.value?.description ?? '';
  if (!raw || !product.value?.long_description) return '';
  return plainText(DOMPurify.sanitize(raw));
});

const safeDescription = computed(() => {
  const raw = product.value?.long_description ?? product.value?.description ?? '';
  return raw ? DOMPurify.sanitize(raw) : '';
});

/** Meta description: the short description, else the long one cut to a sentence. */
const plainDescription = computed(() => {
  const lead = shortDescription.value || plainText(safeDescription.value);
  return lead.length > 160 ? `${lead.slice(0, 157).trimEnd()}…` : lead;
});

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
  // The admin's extra pictures come before the Icecat ones.
  for (const url of product.value?.gallery_urls ?? []) {
    if (url && !urls.includes(url)) urls.push(url);
  }
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

const canonicalHref = computed(() => {
  if (!product.value) return '';
  return absoluteUrl(route.path) ?? '';
});

/** schema.org availability of the shown product (R8 / U6). */
const schemaAvailability = computed(() => {
  const a = availability.value;
  if (!a.orderable) return 'https://schema.org/OutOfStock';
  if (a.preorder) return 'https://schema.org/PreOrder';
  return 'https://schema.org/InStock';
});

/** JSON-LD Product + Offer of the page: price in the reference currency. */
const productJsonLd = computed<Record<string, unknown> | null>(() => {
  const p = product.value;
  if (!p || !canonicalHref.value) return null;
  const data: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: p.name,
    url: canonicalHref.value,
    image: gallery.value.slice(0, 5),
    description: plainDescription.value || undefined,
    sku: p.vendor_part_number ?? p.supplier_sku ?? undefined,
    gtin13: p.ean ?? undefined,
    brand: p.manufacturer ? { '@type': 'Brand', name: p.manufacturer } : undefined,
    category: categoryLabel.value ?? undefined,
    itemCondition:
      p.condition === 'refurbished'
        ? 'https://schema.org/RefurbishedCondition'
        : 'https://schema.org/NewCondition',
  };
  if (!isQuote.value) {
    data['offers'] = {
      '@type': 'Offer',
      url: canonicalHref.value,
      price: priceValue.value.toFixed(0),
      priceCurrency: currencyStore.reference,
      availability: schemaAvailability.value,
      itemCondition: data['itemCondition'],
    };
  }
  return data;
});

useMeta(() => {
  const shopName = shopModules.config.shop_name || 'Natimai';
  const title = product.value
    ? t('product.meta_title', { name: product.value.name, shop: shopName })
    : t('product.meta_title_default', { shop: shopName });
  const description = plainDescription.value || t('product.meta_description');
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
  const script: Record<string, Record<string, string>> = {};
  if (mainImage.value) {
    meta['ogImage'] = { property: 'og:image', content: mainImage.value };
  }
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
  // R8 / U6 : structured data for the engines (rich results, breadcrumb).
  if (productJsonLd.value) script['ldProduct'] = jsonLd(productJsonLd.value);
  if (product.value) {
    const crumbs = [
      { name: t('layout.home'), path: '/' },
      { name: t('layout.catalogue'), path: '/catalogue' },
    ];
    for (const crumb of categoryCrumbs.value) {
      crumbs.push({ name: crumb.label, path: `/catalogue?cat=${crumb.id}` });
    }
    crumbs.push({ name: product.value.name, path: route.path });
    const breadcrumb = breadcrumbList(crumbs);
    if (breadcrumb) script['ldBreadcrumb'] = jsonLd(breadcrumb);
  }

  return {
    title,
    meta,
    link,
    script,
  };
});

async function loadProduct() {
  selectedImage.value = null;
  cartError.value = null;
  alertNotice.value = null;
  quantity.value = 1;
  justAdded.value = false;
  showAllSpecs.value = false;
  shippingModes.value = [];
  selectedModeKey.value = null;
  offers.value = null;
  keySpecs.value = [];

  const routeId = typeof route.params.id === 'string' ? route.params.id : null;
  if (!routeId) {
    productDetail.notFound();
    return;
  }

  await productDetail.load(routeId, locale.value);
  const data = product.value;
  selectedOptions.value = {};
  if (!data || data.id !== routeId) return;
  // One variant only: nothing to choose, select it — unless the base
  // product is sold as is, in which case it stays the default.
  if (variants.value?.variants.length === 1 && !data.variants_optional) {
    selectedOptions.value = { ...(variants.value.variants[0]?.variant_options ?? {}) };
  }

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
}

function setQuantity(value: number) {
  quantity.value = Math.max(1, Math.floor(value));
  justAdded.value = false;
}

async function onAddToCart() {
  const target = effectiveProduct.value;
  if (!target) return;
  if (needsVariantChoice.value) {
    cartError.value = t('product.choose_variant');
    return;
  }

  cartError.value = null;
  const ok = await cartStore.addItem(target.id, quantity.value, target);
  if (ok) {
    justAdded.value = true;
    return;
  }
  cartError.value = cartStore.error ?? t('product.add_failed');
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

// The texts follow the visitor's language (R9 / T3).
watch(locale, () => void loadProduct());

// « Complétez votre équipement » (R9 / T7): loaded after the product, client side.
const related = ref<RelatedProductsResponse>({ accessories: [], alternatives: [] });
async function loadRelated() {
  related.value = { accessories: [], alternatives: [] };
  const id = product.value?.id;
  if (!id) return;
  try {
    related.value = await getRelatedProducts(id);
  } catch {
    // a suggestion block that fails to load is simply not shown
  }
}
async function addRelatedToCart(item: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(item.id, 1, item);
  if (ok) uiStore.openCartDrawer(item.id);
  else cartError.value = cartStore.error ?? t('product.add_failed');
}
watch(
  () => product.value?.id,
  () => {
    if (import.meta.env.QUASAR_CLIENT) void loadRelated();
  },
);

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
  // Client only: the SSR pass must not count a view, and a bot-heavy server
  // render would skew the « plus consultés » ranking.
  if (import.meta.env.QUASAR_CLIENT && product.value) void trackProductView(product.value.id);
  void refreshWishlistState();
});

watch(
  () => route.params.id,
  async (current, previous) => {
    if (current && current !== previous) {
      await loadProduct();
      void refreshWishlistState();
    }
  },
);
</script>

<style scoped lang="scss">
.product {
  padding-top: 20px;
  padding-bottom: 96px;
}

.product__related,
.product__reviews {
  margin-top: 48px;
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

.product__lead {
  margin: 12px 0 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--n-ink-2);
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

.product__promo {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: var(--n-ink-2);
}

.product__promo-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-on-accent);
  background: var(--n-accent);
}

.product__promo-price {
  color: var(--n-accent);
}

.product__tax {
  margin-left: 6px;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: var(--n-ink-2);
  vertical-align: middle;
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

.product__departure {
  margin-top: 20px;
  display: flex;
  gap: 10px;
  font-size: 14px;
  line-height: 1.45;
  color: var(--n-ink-2);

  .q-icon {
    flex-shrink: 0;
    margin-top: 1px;
  }
}

.product__refurb {
  margin: 16px 0 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.product__refurb-badge {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 10px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--n-refurb);
  background: var(--n-refurb-soft);
}

.alert-dialog {
  width: min(440px, 100vw - 32px);
  border: 1px solid var(--n-line);
}

.alert-dialog__title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
}

.alert-dialog__text {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--n-ink-2);
}

.product__variants-link {
  margin-top: 4px;
  font-size: 13px;
  color: var(--n-ink-2);

  &:hover {
    color: var(--n-accent);
  }
}

.variants {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.variants__axis {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.variants__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--n-ink-2);
}

.variants__extra {
  margin-left: 6px;
  font-size: 12px;
  color: var(--n-ink-3);
}

.variants__options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.variants__option {
  min-height: 40px;
  padding: 0 14px;
  border: 1px solid var(--n-line-2);
  border-radius: 8px;
  background: var(--n-surface);
  color: var(--n-ink);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: border-color 0.2s ease;

  &:hover {
    border-color: var(--n-ink-3);
  }

  &--active,
  &--active:hover {
    border-color: var(--n-ink);
    box-shadow: inset 0 0 0 1px var(--n-ink);
  }

  &--unavailable {
    border-style: dashed;
    color: var(--n-ink-3);
  }
}

.variants__hint {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 13px;
  color: var(--n-ink-3);
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

.product__wish {
  flex-shrink: 0;
  width: 48px;
  min-height: 48px;

  &--on {
    color: var(--n-accent) !important;
  }
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
  display: flex;
  flex-direction: column;
  font-size: 18px;
  font-weight: 600;

  .product__price-note {
    font-size: 12px;
    font-weight: 400;
  }
}
</style>
