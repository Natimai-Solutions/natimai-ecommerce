<template>
  <div v-if="store.next" class="departure-strip" data-testid="next-departure-banner">
    <div class="departure-strip__inner page-container">
      <q-icon name="ph:calendar-check" size="18px" class="departure-strip__icon" />
      <p class="departure-strip__text">
        <span class="departure-strip__name">Prochain départ groupé « {{ store.next.name }} »</span>
        <span>{{ store.cutoffLabel }}</span>
        <span v-if="store.deliveryLabel" class="departure-strip__delivery">
          {{ store.deliveryLabel }}
        </span>
      </p>
      <router-link :to="{ name: 'how-it-works' }" class="departure-strip__link">
        Comment ça marche ?
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDepartureStore } from 'src/stores/departure';

const store = useDepartureStore();
</script>

<style scoped lang="scss">
.departure-strip {
  border-bottom: 1px solid var(--n-line);
  background: var(--n-surface);
}

.departure-strip__inner {
  min-height: 44px;
  padding-top: 10px;
  padding-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--n-ink-2);
}

.departure-strip__icon {
  flex-shrink: 0;
  color: var(--n-ink);
}

.departure-strip__text {
  margin: 0;
  min-width: 0;
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 2px 16px;
}

.departure-strip__name {
  font-weight: 500;
  color: var(--n-ink);
}

.departure-strip__link {
  flex-shrink: 0;
  color: var(--n-ink);
  text-underline-offset: 3px;

  &:hover {
    color: var(--n-accent);
  }
}

@media (max-width: 767px) {
  .departure-strip__delivery {
    display: none;
  }
}
</style>
