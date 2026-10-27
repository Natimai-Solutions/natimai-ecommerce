<template>
  <span class="star-rating" role="img" :aria-label="$t('reviews.rated', { n: label })">
    <span class="star-rating__base" aria-hidden="true">★★★★★</span>
    <!-- prettier-ignore -->
    <span class="star-rating__fill" :style="{ width: `${percent}%` }" aria-hidden="true">★★★★★</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

/** Five stars filled to `value` (0–5, halves and tenths included). */
const props = defineProps<{ value: number }>();

const clamped = computed(() => Math.min(5, Math.max(0, props.value || 0)));
const percent = computed(() => (clamped.value / 5) * 100);
const label = computed(() => clamped.value.toLocaleString(undefined, { maximumFractionDigits: 1 }));
</script>

<style scoped lang="scss">
.star-rating {
  position: relative;
  display: inline-block;
  font-size: 16px;
  line-height: 1;
  letter-spacing: 1px;
  white-space: nowrap;
}

.star-rating__base {
  color: var(--n-line-2);
}

.star-rating__fill {
  position: absolute;
  top: 0;
  left: 0;
  overflow: hidden;
  color: var(--n-warn);
}
</style>
