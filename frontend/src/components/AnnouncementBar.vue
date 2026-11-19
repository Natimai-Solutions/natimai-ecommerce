<template>
  <div
    class="announcement"
    :class="{ 'announcement--hidden': !visible }"
    :aria-hidden="!visible"
    data-testid="announcement"
  >
    <div v-if="item" class="announcement__inner page-container">
      <p class="announcement__text">{{ item.title }}</p>
      <component
        :is="isInternalLink(item.cta_link) ? 'router-link' : 'a'"
        v-if="item.cta_link"
        v-bind="linkAttrs(item.cta_link)"
        class="announcement__link"
        :tabindex="visible ? undefined : -1"
      >
        {{ item.cta_label || $t('announcement.more') }}
      </component>
      <button
        type="button"
        class="announcement__close"
        :aria-label="$t('announcement.close')"
        :tabindex="visible ? undefined : -1"
        data-testid="announcement-close"
        @click="store.dismiss()"
      >
        <q-icon name="ph:x" size="16px" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';

import { announcementKey, useAnnouncementStore } from '@/stores/announcement';
import { isInternalLink, linkAttrs } from '@/utils/links';

const store = useAnnouncementStore();
const route = useRoute();

const item = computed(() => store.current);
/** Not while paying (checkout, balance, return from the bank): nothing to
 *  distract from it. */
const HIDDEN_ON = new Set(['checkout', 'order-balance', 'payment-return']);
const visible = computed(
  () =>
    !!item.value &&
    !HIDDEN_ON.has(String(route.name ?? '')) &&
    store.dismissed !== announcementKey(item.value),
);

onMounted(() => store.readDismissed());
</script>

<style scoped lang="scss">
.announcement {
  display: grid;
  grid-template-rows: 1fr;
  grid-template-columns: minmax(0, 1fr);
  background: var(--n-ink);
  color: var(--n-bg);
  transition: grid-template-rows 0.2s ease;
  overflow: hidden;
}

.announcement--hidden {
  grid-template-rows: 0fr;
}

.announcement__inner {
  min-height: 0;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  line-height: 1.3;
}

.announcement:not(.announcement--hidden) .announcement__inner {
  padding-top: 8px;
  padding-bottom: 8px;
}

.announcement__text {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  text-align: center;
}

.announcement__link {
  flex: none;
  color: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.announcement__close {
  flex: none;
  display: inline-flex;
  padding: 4px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: inherit;
  cursor: pointer;

  &:focus-visible {
    outline: 2px solid currentColor;
  }
}

@media (max-width: 599px) {
  .announcement__text {
    // One line on a phone: the link stays visible next to it.
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
</style>
