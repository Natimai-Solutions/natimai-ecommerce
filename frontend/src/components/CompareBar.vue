<template>
  <transition name="compare-bar">
    <div
      v-if="compareStore.loaded && compareStore.count > 0 && !onComparePage"
      class="compare-bar"
      role="region"
      :aria-label="$t('compare.bar_label')"
      data-testid="compare-bar"
    >
      <div class="compare-bar__inner page-container">
        <q-icon name="ph:scales" size="20px" class="compare-bar__icon" />
        <span class="compare-bar__text">
          {{ $t('compare.bar_count', { n: compareStore.count, max: COMPARE_MAX }) }}
        </span>
        <q-btn
          flat
          no-caps
          dense
          :label="$t('compare.clear')"
          class="compare-bar__clear"
          @click="compareStore.clear()"
        />
        <q-btn
          unelevated
          no-caps
          color="primary"
          :label="$t('compare.open')"
          :to="{ name: 'compare' }"
          :disable="compareStore.count < 2"
          data-testid="compare-bar-open"
        />
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { COMPARE_MAX, useCompareStore } from '@/stores/compare';

/** Sticky reminder of the comparison shortlist (R8 / confort). */
const compareStore = useCompareStore();
const route = useRoute();
const onComparePage = computed(() => route.name === 'compare');

onMounted(() => compareStore.load());
</script>

<style scoped lang="scss">
.compare-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1500;
  background: var(--n-surface);
  border-top: 1px solid var(--n-line);
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.08);
}

.compare-bar__inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 10px;
  padding-bottom: 10px;
}

.compare-bar__icon {
  color: var(--n-accent);
}

.compare-bar__text {
  flex-grow: 1;
  font-size: 14px;
}

.compare-bar__clear {
  color: var(--n-ink-3);
}

.compare-bar-enter-active,
.compare-bar-leave-active {
  transition:
    transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.2s ease;
}

.compare-bar-enter-from,
.compare-bar-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
