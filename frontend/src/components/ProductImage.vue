<template>
  <div class="product-image" :style="{ aspectRatio: String(ratio) }">
    <img
      v-if="src && !failed"
      :src="src"
      :alt="alt"
      :loading="eager ? 'eager' : 'lazy'"
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
import { ref, watch } from 'vue';

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
  }>(),
  { ratio: 1, glyphSize: '56px', eager: false },
);

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
  border-radius: 8px;
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
