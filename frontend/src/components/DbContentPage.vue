<template>
  <q-page class="legal-page page-container">
    <article class="prose">
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
        <p class="text-muted">Cette page n'est pas encore rédigée.</p>
      </slot>
    </article>
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
