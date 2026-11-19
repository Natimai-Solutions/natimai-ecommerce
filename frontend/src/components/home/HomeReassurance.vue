<template>
  <ul class="reassurance" :class="`reassurance--${items.length}`" data-testid="home-reassurance">
    <li v-for="(item, index) in items" :key="index">
      <component
        :is="item.link ? (isInternalLink(item.link) ? 'router-link' : 'a') : 'div'"
        v-bind="item.link ? linkAttrs(item.link) : {}"
        class="reassurance__item"
      >
        <q-icon :name="REASSURANCE_ICONS[item.icon] ?? 'ph:check-circle'" size="28px" />
        <span>{{ item.text }}</span>
      </component>
    </li>
  </ul>
</template>

<script setup lang="ts">
import type { components } from '@app/api-types';

import { isInternalLink, linkAttrs } from '@/utils/links';

type Item = components['schemas']['HomepageReassurance'];

defineProps<{ items: Item[] }>();

/** The closed list of the back-office (lot A3 / R5), drawn here. */
const REASSURANCE_ICONS: Record<string, string> = {
  truck: 'ph:truck',
  boat: 'ph:boat',
  map_pin: 'ph:map-pin',
  package: 'ph:package',
  lock: 'ph:lock-simple',
  shield: 'ph:shield-check',
  credit_card: 'ph:credit-card',
  seal: 'ph:seal-check',
  chat: 'ph:chat-circle-text',
  phone: 'ph:phone',
  clock: 'ph:clock',
  returns: 'ph:arrow-counter-clockwise',
  tag: 'ph:tag',
  star: 'ph:star',
};
</script>

<style scoped lang="scss">
.reassurance {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (min-width: 1024px) {
  .reassurance--3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .reassurance--4 {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.reassurance__item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 100%;
  padding: 16px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-surface);
  color: var(--n-ink);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
  text-decoration: none;

  .q-icon {
    flex: none;
    color: var(--n-ink-2);
  }
}

a.reassurance__item:hover {
  border-color: var(--n-line-2);
}

@media (max-width: 599px) {
  .reassurance__item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 12px;
  }
}
</style>
