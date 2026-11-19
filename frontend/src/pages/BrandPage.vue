<template>
  <q-page class="brand page-container">
    <div v-if="page.loading && !page.brand" class="brand__head" aria-busy="true">
      <q-skeleton type="rect" width="96px" height="96px" />
      <div class="col">
        <q-skeleton type="text" width="40%" height="36px" />
        <q-skeleton type="text" width="70%" />
      </div>
    </div>

    <div v-else-if="page.error" class="brand__missing">
      <h1 class="brand__title">
        {{ page.error === 'not_found' ? $t('brand.not_found') : $t('brand.load_failed') }}
      </h1>
      <q-btn unelevated no-caps color="primary" :label="$t('brand.see_catalogue')" to="/catalogue" />
    </div>

    <template v-else-if="page.brand">
      <header class="brand__head">
        <img
          v-if="page.brand.logo"
          class="brand__logo"
          :src="page.brand.logo.src"
          :srcset="page.brand.logo.srcset ?? undefined"
          sizes="96px"
          :width="page.brand.logo.width ?? undefined"
          :height="page.brand.logo.height ?? undefined"
          :alt="page.brand.name"
        />
        <div class="brand__intro">
          <h1 class="brand__title">{{ page.brand.name }}</h1>
          <p v-if="page.brand.description" class="brand__text">{{ page.brand.description }}</p>
          <p class="brand__count text-subtle">
            {{ $t('brand.count', { n: page.total }, page.total) }}
          </p>
        </div>
      </header>

      <CartErrorToast v-model="cartError" />

      <p v-if="!page.products.length" class="text-subtle">{{ $t('brand.empty') }}</p>
      <div v-else class="product-grid">
        <ProductCard
          v-for="(product, index) in page.products"
          :key="product.id"
          :product="product"
          :eager="index < 2"
          @add-to-cart="onAddToCart"
          @compare-full="cartError = t('compare.full', { max: COMPARE_MAX })"
        />
      </div>

      <div v-if="page.total > page.products.length" class="brand__more">
        <q-btn
          outline
          no-caps
          color="primary"
          :label="$t('brand.see_all', { name: page.brand.name })"
          :to="{ path: '/catalogue', query: { mfr: page.brand.name } }"
        />
      </div>
    </template>
  </q-page>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

// Server render: the brand is loaded before setup, so that the title and
// description `useMeta` computes once are the brand's (lot BR).
export default defineComponent({
  async preFetch({ store, currentRoute }) {
    // In the browser the page loads it itself (in the visitor's language).
    if (!import.meta.env.QUASAR_SERVER) return;
    const slug = currentRoute.params['slug'];
    if (typeof slug !== 'string') return;
    const [{ useBrandPageStore }, { currentRequestScope }] = await Promise.all([
      import('@/stores/brandPage'),
      import('@/ssr/requestScope'),
    ]);
    await useBrandPageStore(store).load(slug, currentRequestScope()?.locale ?? 'fr');
  },
});
</script>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useMeta } from 'quasar';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import type { components } from '@app/api-types';

import CartErrorToast from '@/components/CartErrorToast.vue';
import ProductCard from '@/components/ProductCard.vue';
import { useBrandPageStore } from '@/stores/brandPage';
import { useCartStore } from '@/stores/cart';
import { COMPARE_MAX } from '@/stores/compare';
import { useShopModulesStore } from '@/stores/shopModules';
import { useUiStore } from '@/stores/ui';
import { absoluteUrl, breadcrumbList, jsonLd, NOINDEX } from '@/utils/seo';

type ProductPublic = components['schemas']['ProductPublic'];

const { t, locale } = useI18n();
const route = useRoute();
const page = useBrandPageStore();
const cartStore = useCartStore();
const uiStore = useUiStore();
const shopModules = useShopModulesStore();
const cartError = ref<string | null>(null);

const slug = computed(() => (typeof route.params.slug === 'string' ? route.params.slug : ''));

async function load() {
  await page.load(slug.value, locale.value);
}

async function onAddToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? t('catalogue.add_failed');
}

useMeta(() => {
  const shop = shopModules.config.shop_name || 'Natimai';
  const brand = page.brand;
  if (!brand) return { title: t('brand.not_found'), meta: NOINDEX };
  const description = brand.description || t('brand.meta_description', { name: brand.name, shop });
  const url = absoluteUrl(`/marque/${brand.slug}`);
  const breadcrumb = breadcrumbList([
    { name: t('layout.catalogue'), path: '/catalogue' },
    { name: brand.name, path: `/marque/${brand.slug}` },
  ]);
  return {
    title: t('brand.meta_title', { name: brand.name, shop }),
    meta: {
      description: { name: 'description', content: description },
      ogTitle: { property: 'og:title', content: brand.name },
      ogDescription: { property: 'og:description', content: description },
      ...(brand.logo ? { ogImage: { property: 'og:image', content: brand.logo.src } } : {}),
    },
    link: url ? { canonical: { rel: 'canonical', href: url } } : {},
    script: breadcrumb ? { ldBreadcrumb: jsonLd(breadcrumb) } : {},
  };
});

onMounted(load);
watch([slug, locale], load);
</script>

<style scoped lang="scss">
.brand {
  padding-top: 24px;
  padding-bottom: 48px;
}

.brand__head {
  display: flex;
  gap: 20px;
  align-items: center;
  margin-bottom: 28px;
}

.brand__logo {
  width: 96px;
  height: 96px;
  object-fit: contain;
  flex: none;
  border-radius: 8px;
  background: var(--n-paper);
  padding: 8px;
  border: 1px solid var(--n-line);
}

.brand__title {
  margin: 0;
  font-size: 32px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.025em;
}

.brand__text {
  margin: 8px 0 0;
  max-width: 70ch;
  color: var(--n-ink-2);
}

.brand__count {
  margin: 6px 0 0;
  font-size: 14px;
}

.brand__missing {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 16px;
}

.brand__more {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}

@media (max-width: 599px) {
  .brand__head {
    align-items: flex-start;
  }

  .brand__logo {
    width: 64px;
    height: 64px;
  }

  .brand__title {
    font-size: 26px;
  }
}
</style>
