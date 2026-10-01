<template>
  <div v-if="store.next" class="departure-strip" data-testid="next-departure-banner">
    <router-link :to="{ name: 'how-it-works' }" class="departure-strip__inner page-container">
      <q-icon name="ph:calendar-check" size="18px" class="departure-strip__icon" />
      <p class="departure-strip__text">
        <span class="departure-strip__name">
          <span class="gt-sm">{{ $t('departure.next_long') }}</span
          ><span class="lt-md">{{ $t('departure.next_short') }}</span> « {{ store.next.name }} »
        </span>
        <span>{{ nextCutoff }}</span>
        <span v-if="nextDelivery" class="departure-strip__delivery">
          {{ nextDelivery }}
        </span>
      </p>
      <span class="departure-strip__link">{{ $t('departure.how') }}</span>
      <q-icon name="ph:caret-right" size="16px" class="departure-strip__chevron" />
    </router-link>
  </div>
</template>

<script setup lang="ts">
import { useDepartureLabels } from '@/composables/useDepartureLabels';
import { useDepartureStore } from '@/stores/departure';

const store = useDepartureStore();
const { nextCutoff, nextDelivery } = useDepartureLabels();
</script>

<style scoped lang="scss">
.departure-strip {
  border-bottom: 1px solid var(--n-line);
  background: var(--n-surface);
}

.departure-strip__inner {
  min-height: 44px;
  text-decoration: none;
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
  text-decoration: underline;
  text-underline-offset: 3px;
}

.departure-strip__inner:hover .departure-strip__link {
  color: var(--n-accent);
}

.departure-strip__chevron {
  display: none;
  flex-shrink: 0;
  color: var(--n-ink-3);
}

@media (max-width: 767px) {
  .departure-strip__text {
    font-size: 12px;
  }

  .departure-strip__delivery,
  .departure-strip__link {
    display: none;
  }

  .departure-strip__chevron {
    display: block;
  }
}
</style>
