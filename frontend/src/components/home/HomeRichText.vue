<template>
  <div
    class="rich-block"
    :class="{ 'rich-block--media': !!section.image, 'rich-block--left': imageLeft }"
    data-testid="home-rich-text"
  >
    <!-- eslint-disable-next-line vue/no-v-html -- nettoyé par DOMPurify -->
    <div class="rich-block__body" v-html="html" />
    <img
      v-if="section.image"
      class="rich-block__media"
      :src="section.image.src"
      :srcset="section.image.srcset ?? undefined"
      sizes="(max-width: 1023px) 100vw, 40vw"
      :width="section.image.width ?? undefined"
      :height="section.image.height ?? undefined"
      :alt="section.image.alt"
      loading="lazy"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import DOMPurify from 'isomorphic-dompurify';

import type { HomepageSection } from '@/api/homepage';

const props = defineProps<{ section: HomepageSection }>();

/** Written in the back-office, never shown unclean (server render included). */
const html = computed(() => DOMPurify.sanitize(props.section.body_html ?? ''));
const imageLeft = computed(() => props.section.config?.['image_side'] === 'left');
</script>

<style scoped lang="scss">
.rich-block {
  display: grid;
  gap: 24px;
  align-items: center;
}

@media (min-width: 1024px) {
  .rich-block--media {
    grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  }

  .rich-block--media.rich-block--left {
    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);

    .rich-block__media {
      order: -1;
    }
  }
}

.rich-block__body {
  max-width: 70ch;
  color: var(--n-ink-2);
  line-height: 1.6;

  :deep(h2),
  :deep(h3) {
    color: var(--n-ink);
    margin: 0 0 12px;
  }

  :deep(p) {
    margin: 0 0 12px;
  }

  :deep(a) {
    color: var(--n-ink);
  }
}

.rich-block__media {
  width: 100%;
  height: auto;
  border-radius: 8px;
  object-fit: cover;
}
</style>
