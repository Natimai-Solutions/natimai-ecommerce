<template>
  <q-page class="home">
    <section
      class="home-hero page-container"
      :class="{ 'home-hero--media': heroImage }"
      aria-labelledby="home-hero-title"
      data-testid="home-hero"
    >
      <div class="home-hero__copy">
        <h1 id="home-hero-title" class="home-hero__title">
          {{ hero?.title || $t('home.hero_title') }}
        </h1>
        <p v-if="heroLead" class="home-hero__lead">{{ heroLead }}</p>
        <div class="home-hero__actions">
          <q-btn
            unelevated
            color="primary"
            :label="hero?.cta_label || $t('home.see_catalogue')"
            icon-right="ph:arrow-right"
            v-bind="linkProps(hero?.cta_link || '/catalogue')"
            class="home-hero__cta"
          />
        </div>
      </div>
      <div v-if="heroImage" class="home-hero__media">
        <img
          :src="heroImage.src"
          :srcset="heroImage.srcset ?? undefined"
          sizes="(max-width: 1023px) 100vw, 50vw"
          :width="heroImage.width ?? undefined"
          :height="heroImage.height ?? undefined"
          :alt="heroImage.alt"
          loading="eager"
          fetchpriority="high"
          decoding="async"
        />
      </div>
    </section>

    <CartErrorToast v-model="cartError" />

    <div v-if="home.preview" class="home-preview page-container" data-testid="home-preview">
      <AppNotice :tone="home.previewFailed ? 'error' : 'warning'" dense>
        {{
          home.previewFailed
            ? $t('home.preview_failed')
            : $t('home.preview_notice', {
                date: home.preview.at ? previewDate(home.preview.at) : $t('home.preview_now'),
                audience:
                  home.preview.scope === 'customer'
                    ? $t('home.preview_customers')
                    : $t('home.preview_visitors'),
              })
        }}
      </AppNotice>
    </div>

    <template v-for="part in parts" :key="part.key">
      <section
        v-if="part.type === 'banners'"
        class="home-section page-container"
        :aria-label="$t('home.featured_aria')"
        data-testid="home-banners"
      >
        <ul class="banners" :class="`banners--${Math.min(part.items.length, 3)}`">
          <li v-for="banner in part.items" :key="banner.id">
            <component
              :is="banner.cta_link ? (isInternal(banner.cta_link) ? 'router-link' : 'a') : 'div'"
              v-bind="banner.cta_link ? linkAttrs(banner.cta_link) : {}"
              class="banner"
            >
              <span v-if="banner.image" class="banner__media">
                <img
                  :src="banner.image.src"
                  :srcset="banner.image.srcset ?? undefined"
                  sizes="(max-width: 599px) 100vw, 50vw"
                  :width="banner.image.width ?? undefined"
                  :height="banner.image.height ?? undefined"
                  :alt="banner.image.alt"
                  loading="lazy"
                  decoding="async"
                />
              </span>
              <span class="banner__text">
                <span class="banner__title">{{ banner.title }}</span>
                <span v-if="banner.subtitle" class="banner__subtitle">{{ banner.subtitle }}</span>
                <span v-if="banner.cta_link" class="banner__cta">
                  {{ banner.cta_label || $t('home.discover') }}
                  <q-icon name="ph:arrow-right" size="16px" />
                </span>
              </span>
            </component>
          </li>
        </ul>
      </section>

      <section
        v-else-if="part.type === 'categories' && part.tiles.length"
        class="home-section page-container"
        :aria-labelledby="`home-section-${part.key}`"
      >
        <div class="home-section__head">
          <h2 :id="`home-section-${part.key}`" class="home-section__title">
            {{ part.section.title || $t('home.categories') }}
          </h2>
          <router-link :to="{ name: 'catalogue' }" class="home-section__link">
            {{ $t('home.all') }}
            <q-icon name="ph:arrow-right" size="16px" />
          </router-link>
        </div>
        <p v-if="part.section.subtitle" class="home-section__lead">{{ part.section.subtitle }}</p>
        <ul class="category-tiles">
          <li v-for="category in part.tiles" :key="category.id">
            <router-link
              :to="{ name: 'catalogue', query: { cat: category.id } }"
              class="category-tile"
              data-testid="home-category"
            >
              <span class="category-tile__media">
                <img
                  v-if="category.image_url"
                  :src="category.image_url"
                  :srcset="category.image_srcset ?? mediaSrcset(category.image_url)"
                  sizes="(max-width: 599px) 50vw, 240px"
                  :alt="category.image_alt ?? ''"
                  loading="lazy"
                  decoding="async"
                  class="category-tile__img"
                />
                <q-icon v-else name="ph:squares-four" size="32px" class="category-tile__glyph" />
              </span>
              <span class="category-tile__name">{{ categoryTitle(category) }}</span>
            </router-link>
          </li>
        </ul>
      </section>

      <section
        v-else-if="part.type === 'products' && part.section.products?.length"
        class="home-section page-container"
        :aria-labelledby="`home-section-${part.key}`"
      >
        <div class="home-section__head">
          <h2 :id="`home-section-${part.key}`" class="home-section__title">
            {{ part.section.title || defaultTitle(part.section.kind) }}
          </h2>
          <span
            v-if="
              part.section.kind === 'popular' ||
              (part.section.kind === 'collection' &&
                ['popular', 'best_sellers'].includes(String(part.section.config?.['source'])))
            "
            class="home-section__hint"
          >
            {{ $t('home.last_days', { days: popularDays(part.section) }) }}
          </span>
        </div>
        <p v-if="part.section.subtitle" class="home-section__lead">{{ part.section.subtitle }}</p>
        <!-- A grid, or one row that scrolls sideways (R2: « carrousel »). -->
        <div
          :class="part.section.config?.['layout'] === 'carousel' ? 'product-row' : 'product-grid'"
          :data-testid="`home-${part.section.kind}`"
          :tabindex="part.section.config?.['layout'] === 'carousel' ? 0 : undefined"
          :role="part.section.config?.['layout'] === 'carousel' ? 'region' : undefined"
          :aria-label="
            part.section.config?.['layout'] === 'carousel'
              ? part.section.title || defaultTitle(part.section.kind)
              : undefined
          "
        >
          <ProductCard
            v-for="product in part.section.products"
            :key="product.id"
            :product="product"
            @add-to-cart="onAddToCart"
            @compare-full="compareFull"
          />
        </div>
      </section>

      <section
        v-else-if="part.type === 'reassurance' && part.section.reassurance?.length"
        class="home-section page-container"
        :aria-label="part.section.title || $t('home.reassurance')"
      >
        <h2 v-if="part.section.title" class="home-section__title home-section__title--solo">
          {{ part.section.title }}
        </h2>
        <HomeReassurance :items="part.section.reassurance" />
      </section>

      <section
        v-else-if="part.type === 'brands' && part.section.brands?.length"
        class="home-section page-container"
        :aria-labelledby="`home-section-${part.key}`"
      >
        <div class="home-section__head">
          <h2 :id="`home-section-${part.key}`" class="home-section__title">
            {{ part.section.title || $t('home.brands') }}
          </h2>
        </div>
        <p v-if="part.section.subtitle" class="home-section__lead">{{ part.section.subtitle }}</p>
        <HomeBrandStrip :brands="part.section.brands" />
      </section>

      <HomePersonal
        v-else-if="part.type === 'personal'"
        :section="part.section"
        @add-to-cart="onAddToCart"
        @compare-full="compareFull"
      />

      <section
        v-else-if="part.type === 'rich_text' && part.section.body_html"
        class="home-section page-container"
        :aria-labelledby="part.section.title ? `home-section-${part.key}` : undefined"
      >
        <h2
          v-if="part.section.title"
          :id="`home-section-${part.key}`"
          class="home-section__title home-section__title--solo"
        >
          {{ part.section.title }}
        </h2>
        <HomeRichText :section="part.section" />
      </section>
    </template>

    <div v-if="home.failed && !home.loading" class="page-container home__notice">
      <AppNotice tone="error" data-testid="home-unavailable">
        {{ $t('home.unavailable') }}
        <template #action>
          <q-btn flat no-caps color="primary" :label="$t('home.retry')" @click="home.reload()" />
        </template>
      </AppNotice>
    </div>

    <section v-else-if="showSkeleton" class="home-section page-container" aria-busy="true">
      <div class="product-grid">
        <div v-for="n in 4" :key="n" class="skeleton-card">
          <q-skeleton square class="skeleton-card__media" />
          <q-skeleton type="text" width="40%" />
          <q-skeleton type="text" width="90%" />
        </div>
      </div>
    </section>
  </q-page>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

// Server render: the sections and the SEO texts typed in the admin are
// loaded before setup, so the title `useMeta` computes once is theirs (A4).
export default defineComponent({
  async preFetch({ store }) {
    const { useHomeStore } = await import('@/stores/home');
    await useHomeStore(store).load();
  },
});
</script>

<script setup lang="ts">
import { mediaSrcset } from '@/utils/mediaSrcset';
import { isInternalLink, linkAttrs } from '@/utils/links';
import CartErrorToast from '@/components/CartErrorToast.vue';
import { useI18n } from 'vue-i18n';
import { useShopModulesStore } from '@/stores/shopModules';
import { computed, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useMeta } from 'quasar';
import { jsonLd, publicSiteUrl } from '@/utils/seo';
import type { components } from '@app/api-types';

import AppNotice from '@app/ui/AppNotice.vue';
import ProductCard from '@/components/ProductCard.vue';
import HomeBrandStrip from '@/components/home/HomeBrandStrip.vue';
import HomeReassurance from '@/components/home/HomeReassurance.vue';
import HomeRichText from '@/components/home/HomeRichText.vue';
import HomePersonal from '@/components/home/HomePersonal.vue';
import { useAuthStore } from '@/stores/auth';
import { useCartStore } from '@/stores/cart';
import {
  previewFromHash,
  type HomepageSection,
  type PreviewParams,
} from '@/api/homepage';
import { useRoute, useRouter } from 'vue-router';
import { useAnnouncementStore } from '@/stores/announcement';
import { categoryTitle, useHomeStore } from '@/stores/home';
import { useUiStore } from '@/stores/ui';
import { COMPARE_MAX } from '@/stores/compare';

const { t, locale } = useI18n({ useScope: 'global' });
const shopModules = useShopModulesStore();

type ProductPublic = components['schemas']['ProductPublic'];

const home = useHomeStore();
const route = useRoute();
const router = useRouter();

const PREVIEW_KEY = 'homepage-preview';
function rememberPreview(params: PreviewParams | null): void {
  try {
    if (params) window.sessionStorage.setItem(PREVIEW_KEY, JSON.stringify(params));
    else window.sessionStorage.removeItem(PREVIEW_KEY);
  } catch {
    // Blocked storage: a reload simply shows the public page.
  }
}
function rememberedPreview(): PreviewParams | null {
  try {
    const raw = window.sessionStorage.getItem(PREVIEW_KEY);
    return raw ? (JSON.parse(raw) as PreviewParams) : null;
  } catch {
    return null;
  }
}
const announcement = useAnnouncementStore();
const authStore = useAuthStore();
const cartStore = useCartStore();
const uiStore = useUiStore();
const cartError = ref<string | null>(null);
// Déclarés avant `useMeta` : Quasar évalue le callback dès l'appel.
/** The hero of this page: the first section when it is one (the API puts it
 *  first), else the shop's default title and lead. */
const hero = computed(() => {
  const first = home.sections[0];
  return first?.kind === 'hero' ? first : null;
});
const heroImage = computed(() => hero.value?.image ?? null);

/** A category tile: a chosen one may carry the srcset of its own image. */
type CategoryPublic = components['schemas']['CategoryPublic'] & { image_srcset?: string | null };
type Part =
  | { type: 'banners'; key: string; items: HomepageSection[] }
  | { type: 'categories'; key: string; section: HomepageSection; tiles: CategoryPublic[] }
  | { type: 'products'; key: string; section: HomepageSection }
  | {
      type: 'reassurance' | 'brands' | 'rich_text' | 'personal';
      key: string;
      section: HomepageSection;
    };

/** The sections after the hero, in order; banners next to each other share
 *  one grid, as before. */
const parts = computed<Part[]>(() => {
  const result: Part[] = [];
  for (const section of home.sections) {
    if (section.kind === 'hero') continue;
    if (section.kind === 'banner') {
      const last = result[result.length - 1];
      if (last?.type === 'banners') last.items.push(section);
      else result.push({ type: 'banners', key: section.id, items: [section] });
    } else if (section.kind === 'categories') {
      const limit = Number(section.config?.['limit'] ?? 8);
      // Manual mode: the categories chosen in the admin, in their order.
      const tiles: CategoryPublic[] = section.categories
        ? section.categories.map((c) => ({
            ...(home.categories.find((full) => full.id === c.id) ?? ({} as CategoryPublic)),
            id: c.id,
            name: c.title,
            display_name: c.title,
            image_url: c.image_url ?? null,
            image_srcset: c.image_srcset ?? null,
          }))
        : home.categoryTiles(limit);
      result.push({ type: 'categories', key: section.id, section, tiles });
    } else if (['featured', 'popular', 'collection'].includes(section.kind)) {
      result.push({ type: 'products', key: section.id, section });
    } else if (section.kind === 'reassurance') {
      result.push({ type: 'reassurance', key: section.id, section });
    } else if (section.kind === 'brand_strip') {
      result.push({ type: 'brands', key: section.id, section });
    } else if (section.kind === 'personal') {
      result.push({ type: 'personal', key: section.id, section });
    } else if (section.kind === 'rich_text') {
      result.push({ type: 'rich_text', key: section.id, section });
    }
  }
  return result;
});

function previewDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleString(locale.value, {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Pacific/Tahiti',
      });
}

function defaultTitle(kind: string): string {
  if (kind === 'popular') return t('home.popular');
  if (kind === 'collection') return t('home.selection');
  return t('home.favourites');
}

function popularDays(section: HomepageSection): number {
  return Number(section.config?.['days'] ?? 30);
}

useMeta(() => {
  const shopName = shopModules.config.shop_name || 'Natimai';
  // Typed in the admin (lot A4 / R11), else the storefront's own texts.
  const title = home.seo?.title || t('home.meta_title', { shop: shopName });
  const description = home.seo?.description || t('home.meta_description');
  const siteUrl = publicSiteUrl();
  const meta: Record<string, { name?: string; property?: string; content: string }> = {
    description: { name: 'description', content: description },
    ogTitle: { property: 'og:title', content: title },
    ogDescription: { property: 'og:description', content: description },
    ogType: { property: 'og:type', content: 'website' },
    ogSiteName: { property: 'og:site_name', content: shopName },
  };
  const link: Record<string, { rel: string; href: string }> = {};
  const script: Record<string, Record<string, string>> = {};
  if (siteUrl) {
    meta['ogUrl'] = { property: 'og:url', content: `${siteUrl}/` };
    link['canonical'] = { rel: 'canonical', href: `${siteUrl}/` };
    if (heroImage.value?.src) {
      meta['ogImage'] = { property: 'og:image', content: heroImage.value.src };
    }
    // R8 / U6 : who the site is, and its search box, for the engines.
    script['ldWebsite'] = jsonLd({
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      name: shopName,
      url: `${siteUrl}/`,
      inLanguage: locale.value,
      potentialAction: {
        '@type': 'SearchAction',
        target: {
          '@type': 'EntryPoint',
          urlTemplate: `${siteUrl}/catalogue?q={search_term_string}`,
        },
        'query-input': 'required name=search_term_string',
      },
    });
    const logo = shopModules.config.branding?.logo?.src;
    script['ldOrganization'] = jsonLd({
      '@context': 'https://schema.org',
      '@type': 'Organization',
      name: shopName,
      url: `${siteUrl}/`,
      ...(logo ? { logo } : {}),
      ...(shopModules.config.social_links?.length
        ? { sameAs: shopModules.config.social_links }
        : {}),
      // Lot A5 / R11: where a customer reaches the shop (the messaging).
      contactPoint: {
        '@type': 'ContactPoint',
        contactType: 'customer service',
        url: `${siteUrl}/contact`,
        availableLanguage: shopModules.config.available_locales ?? [locale.value],
      },
    });
  }
  return { title, meta, link, script };
});

// Tant que rien n'est arrivé, des squelettes gardent la place des produits.
const FALLBACK_LEAD = computed(() => t('home.lead'));

const heroLead = computed(() => (hero.value ? hero.value.subtitle : FALLBACK_LEAD.value));

/** Lien d'un bloc : chemin du site (routeur) ou adresse https (nouvel onglet). */
const isInternal = isInternalLink;

/** Mêmes liens pour un q-btn (to ou href). */
function linkProps(link: string): Record<string, string> {
  return linkAttrs(link);
}

const showSkeleton = computed(() => !home.loaded && !home.sections.length);

function compareFull() {
  cartError.value = t('compare.full', { max: COMPARE_MAX });
}

async function onAddToCart(product: ProductPublic) {
  cartError.value = null;
  const ok = await cartStore.addItem(product.id, 1, product);
  if (ok) {
    uiStore.openCartDrawer(product.id);
    return;
  }
  cartError.value = cartStore.error ?? t('home.add_failed');
}

onServerPrefetch(() => home.load());
onMounted(async () => {
  // The admin's preview link (#apercu=…): drafts, a date, an audience.
  // The token leaves the address at once (not in the history, nor in an
  // error report: Sentry records the URL), through the router so that its
  // own state forgets it too; it is kept for this tab only, for a reload.
  let preview = previewFromHash(window.location.hash);
  if (preview) {
    rememberPreview(preview);
    await router.replace({ path: route.path, query: route.query, hash: '' });
  } else {
    preview = rememberedPreview();
  }
  if (preview) {
    await home.startPreview(preview);
    if (home.previewFailed) rememberPreview(null);
    announcement.showPreview(home.previewAnnouncement);
    return;
  }
  await home.load();
  // Rendered by the server for a visitor: a signed-in customer gets their own
  // page (sections of their audience, prices of their price group).
  await home.syncAudience();
});
// Signing in or out on the page changes it too.
watch(
  () => authStore.isAuthenticated,
  () => void home.syncAudience(),
);
// Blocks, category tiles and product names follow the visitor's language (R9 / T3).
watch(locale, () => void home.reload());
</script>

<style scoped lang="scss">
.home {
  padding-bottom: 96px;
}

.home-hero {
  padding-top: 72px;
  padding-bottom: 56px;

  @media (max-width: 599px) {
    padding-top: 40px;
    padding-bottom: 32px;
  }
}

.home-hero__copy {
  max-width: 720px;
}

.home-hero--media {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 56px;
  align-items: center;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 32px;
  }
}

.home-hero__media {
  overflow: hidden;
  border-radius: var(--n-radius-lg);
  background: var(--n-tile);
  aspect-ratio: 4 / 3;

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
  }
}

.banners {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 20px;

  &--2,
  &--3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  &--3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  @media (max-width: 599px) {
    &--2,
    &--3 {
      grid-template-columns: minmax(0, 1fr);
    }
  }
}

.banner {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: var(--n-radius-lg);
  background: var(--n-tile);
  color: var(--n-ink);
  text-decoration: none;
  transition: background-color 0.2s ease;

  .banners--1 & {
    @media (min-width: 600px) {
      flex-direction: row;
      align-items: stretch;

      .banner__media {
        flex: 0 0 50%;
        aspect-ratio: auto;
        min-height: 280px;
      }

      .banner__text {
        justify-content: center;
        padding: 40px;
      }
    }
  }
}

a.banner:hover {
  background: var(--n-tile-hover);

  .banner__media img {
    transform: scale(1.02);
  }

  .banner__cta {
    color: var(--n-accent);
  }
}

.banner__media {
  aspect-ratio: 16 / 9;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    display: block;
    object-fit: cover;
    transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  }
}

.banner__text {
  flex-grow: 1;
  padding: 22px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.banner__title {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.015em;
}

.banner__subtitle {
  font-size: 15px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

.banner__cta {
  margin-top: auto;
  padding-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  transition: color 0.2s ease;
}

.home-hero__title {
  margin: 0;
  font-size: clamp(36px, 5vw, 60px);
  font-weight: 600;
  line-height: 1.02;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.home-hero__lead {
  max-width: 56ch;
  margin: 20px 0 0;
  font-size: 17px;
  line-height: 1.55;
  color: var(--n-ink-2);
  text-wrap: pretty;
}

.home-hero__actions {
  margin-top: 32px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.home-hero__cta {
  min-height: 48px;
  padding: 0 22px;
}

.home__notice {
  margin-bottom: 24px;
}

.home-preview {
  padding-top: 16px;
}

.home-section {
  padding-top: 48px;
  border-top: 1px solid var(--n-line);
  margin-top: 8px;

  & + & {
    margin-top: 56px;
  }
}

.product-row {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(220px, calc((100% - 3 * 20px) / 4));
  gap: 20px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  padding-bottom: 8px;
  overscroll-behavior-x: contain;

  > * {
    scroll-snap-align: start;
  }

  &:focus-visible {
    outline: 2px solid var(--n-ink);
    outline-offset: 4px;
  }
}

@media (max-width: 599px) {
  .product-row {
    grid-auto-columns: 72%;
    gap: 12px;
  }
}

.home-section__title--solo {
  margin-bottom: 20px;
}

.home-section__head {
  margin-bottom: 24px;
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.home-section__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.015em;
}

.home-section__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}

.home-section__lead {
  margin: -8px 0 16px;
  font-size: 15px;
  color: var(--n-ink-2);
  max-width: 64ch;
}

.home-section__link {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.category-tiles {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  // auto-fill : autant de colonnes de 180 à 280 px que la ligne en contient,
  // l'espace restant à droite. Avec deux ou trois catégories sur un grand
  // écran, les tuiles restent côte à côte au lieu d'être réparties aux deux
  // bouts de la ligne (03/10/2026) ; une tuile seule garde une taille lisible.
  grid-template-columns: repeat(auto-fill, minmax(180px, 280px));
  justify-content: start;
  gap: 20px;

  // Mobile : une rangée qui défile, plutôt qu'une grille à tuile orpheline.
  @media (max-width: 599px) {
    grid-auto-flow: column;
    grid-template-columns: none;
    grid-auto-columns: 42%;
    gap: 12px;
    margin-right: -16px;
    padding-right: 16px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    scrollbar-width: none;

    > li {
      scroll-snap-align: start;
    }
  }
}

.category-tile {
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--n-ink);
  text-decoration: none;

  &:hover .category-tile__media {
    background: var(--n-tile-hover);
  }

  &:hover .category-tile__img {
    transform: scale(1.03);
  }

  &:hover .category-tile__name {
    color: var(--n-accent);
  }
}

.category-tile__media {
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: var(--n-radius);
  background: var(--n-tile);
  transition: background-color 0.2s ease;
}

.category-tile__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.category-tile__glyph {
  color: var(--n-glyph);
}

.category-tile__name {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.3;
  transition: color 0.2s ease;
}
</style>
