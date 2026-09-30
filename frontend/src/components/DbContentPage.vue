<template>
  <q-page class="legal-page q-pa-md">
    <div class="legal-page__content">
      <template v-if="page">
        <h1 class="text-h4 text-weight-bold q-mb-lg">{{ page.title }}</h1>
        <!-- eslint-disable-next-line vue/no-v-html -- sanitised by DOMPurify -->
        <div class="db-page-body" data-testid="db-page-body" v-html="safeHtml"></div>
      </template>
      <div v-else-if="loading" class="text-center q-pa-lg">
        <q-spinner color="primary" size="2em" />
      </div>
      <slot v-else name="fallback">
        <h1 class="text-h4 text-weight-bold q-mb-lg">{{ fallbackTitle }}</h1>
        <p class="text-grey-7">Cette page n'est pas encore rédigée.</p>
      </slot>
    </div>
  </q-page>
</template>

<script setup lang="ts">
/**
 * Renders the editable page `slug` when the back-office published one, else
 * the `fallback` slot (the hard-coded legal text, for instance). Fetched
 * during SSR so the page arrives complete.
 */
import DOMPurify from 'isomorphic-dompurify';
import { computed, onMounted, onServerPrefetch, ref } from 'vue';
import { getPage, type ContentPage } from '@/api/pages';

const props = defineProps<{ slug: string; fallbackTitle?: string }>();

const page = ref<ContentPage | null>(null);
const loading = ref(true);

async function load(): Promise<void> {
  try {
    page.value = await getPage(props.slug);
  } catch {
    page.value = null; // not published: the fallback slot shows
  } finally {
    loading.value = false;
  }
}

const safeHtml = computed(() => (page.value ? DOMPurify.sanitize(page.value.body_html) : ''));

onServerPrefetch(load);
onMounted(() => {
  if (loading.value) void load();
});
</script>

<style scoped lang="scss">
.legal-page__content {
  width: min(860px, 100%);
  margin: 0 auto;
  line-height: 1.65;
}
.db-page-body :deep(h2) {
  font-size: 1.25rem;
  margin: 1.5rem 0 0.5rem;
}
.db-page-body :deep(h3) {
  font-size: 1.05rem;
  margin: 1.25rem 0 0.4rem;
}
.db-page-body :deep(img) {
  max-width: 100%;
}
</style>
