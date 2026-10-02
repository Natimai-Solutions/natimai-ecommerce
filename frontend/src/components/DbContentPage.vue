<template>
  <q-page class="legal-page page-container">
    <article class="prose">
      <AppNotice
        v-if="frenchOnly && !loading"
        tone="info"
        icon="ph:translate"
        class="q-mb-md"
        data-testid="content-french-only"
      >
        {{ $t('content.french_only') }}
      </AppNotice>
      <template v-if="page">
        <h1>{{ page.title }}</h1>
        <!-- eslint-disable-next-line vue/no-v-html -- sanitised by DOMPurify -->
        <div class="db-page-body" data-testid="db-page-body" v-html="safeHtml"></div>
      </template>
      <div v-else-if="loading" aria-busy="true">
        <q-skeleton type="text" width="60%" height="48px" />
        <q-skeleton v-for="n in 4" :key="n" type="text" />
      </div>
      <slot v-else name="fallback">
        <h1>{{ fallbackTitle }}</h1>
        <p class="text-muted">{{ $t('content.not_written') }}</p>
      </slot>
    </article>
  </q-page>
</template>

<script setup lang="ts">
/**
 * Renders the editable page `slug` when the back-office published one, else
 * the `fallback` slot (the hard-coded legal text, for instance). Fetched
 * during SSR so the page arrives complete.
 *
 * The API serves the page in the visitor's language when the back-office
 * translated it (R9 / T3); otherwise the default-language text shows with a
 * notice that it is the reference version (R7).
 */
import DOMPurify from 'isomorphic-dompurify';
import { computed, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import { getPage, type ContentPage } from '@/api/pages';
import { usePageMeta } from '@/composables/usePageMeta';
import { useShopModulesStore } from '@/stores/shopModules';

const props = defineProps<{ slug: string; fallbackTitle?: string }>();

const { locale } = useI18n({ useScope: 'global' });
const page = ref<ContentPage | null>(null);
const loading = ref(true);
/** Served in the shop's default language although the interface is in another one. */
const frenchOnly = computed(
  () => page.value !== null && (page.value.lang ?? 'fr') !== locale.value,
);

async function fetchPage(slug: string): Promise<ContentPage | null> {
  try {
    return await getPage(slug);
  } catch {
    return null; // not published
  }
}

async function load(): Promise<void> {
  loading.value = true;
  try {
    // Not published: the fallback slot shows.
    page.value = await fetchPage(props.slug);
  } finally {
    loading.value = false;
  }
}

watch(locale, () => void load());

const safeHtml = computed(() => (page.value ? DOMPurify.sanitize(page.value.body_html) : ''));

// R8 / U6 : the page's own title and first words as description, canonical link.
const shopModules = useShopModulesStore();
usePageMeta(() => {
  const title = page.value?.title ?? props.fallbackTitle ?? '';
  const text = safeHtml.value
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return {
    title: `${title} | ${shopModules.config.shop_name || 'Natimai'}`,
    description: text ? text.slice(0, 157) + (text.length > 157 ? '…' : '') : null,
  };
});

onServerPrefetch(load);
onMounted(() => {
  if (loading.value) void load();
});
</script>
