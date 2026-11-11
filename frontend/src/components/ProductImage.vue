<template>
  <div class="product-image" :style="{ aspectRatio: String(ratio) }">
    <img
      v-if="src && !failed"
      :src="src"
      :srcset="srcset"
      :sizes="srcset ? sizes : undefined"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
      :fetchpriority="eager ? 'high' : undefined"
      decoding="async"
      class="product-image__img"
      @error="failed = true"
    />
    <q-icon
      v-else
      name="ph:package"
      class="product-image__glyph"
      :size="glyphSize"
      role="img"
      :aria-label="alt"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import { mediaSrcset } from '@/utils/mediaSrcset';

/**
 * Photo produit posée sur un « puits » neutre, en entier (jamais recadrée).
 * Les photos fournisseur sont des détourés sur fond blanc : le mode de fusion
 * `multiply` fond ce blanc dans le puits. Sans photo, ou si elle ne charge
 * pas, un glyphe Phosphor tient la place.
 */
const props = withDefaults(
  defineProps<{
    src: string | null | undefined;
    alt: string;
    ratio?: number;
    glyphSize?: string;
    eager?: boolean;
    /** Rendered width, for the browser to pick a size (cards by default). */
    sizes?: string;
  }>(),
  {
    ratio: 1,
    glyphSize: '56px',
    eager: false,
    sizes: '(max-width: 599px) 50vw, (max-width: 1023px) 33vw, 300px',
  },
);

/** Smaller WebP widths of a shop upload; `eager` marks the LCP image. */
const srcset = computed(() => mediaSrcset(props.src));

const failed = ref(false);
watch(
  () => props.src,
  () => {
    failed.value = false;
  },
);
</script>

<style scoped lang="scss">
.product-image {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: var(--n-radius);
  background: var(--n-photo);
  transition: background-color 0.25s ease;
}

.product-image__img {
  width: 100%;
  height: 100%;
  padding: 10%;
  object-fit: contain;
  mix-blend-mode: multiply;
  transition: transform 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}

.product-image__glyph {
  color: var(--n-photo-glyph);
}
</style>
