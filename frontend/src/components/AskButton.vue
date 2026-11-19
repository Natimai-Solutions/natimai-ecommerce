<template>
  <q-btn
    v-if="shop.isOn('messaging')"
    flat
    no-caps
    color="primary"
    icon="ph:chat-circle-text"
    :label="label"
    :to="target"
    class="ask-button"
    data-testid="ask-button"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue';

import { useAuthStore } from '@/stores/auth';
import { useShopModulesStore } from '@/stores/shopModules';

/**
 * « A question? »: opens a pre-filled request about what the page shows —
 * the customer's messages (topic and attachment set), or the public contact
 * page for a visitor (topic and subject set). Chantier accueil et
 * messagerie, lot MSG3.
 */
const props = defineProps<{
  label: string;
  topic: string;
  contextType?: 'order' | 'product' | 'group_request';
  contextId?: string;
  /** Subject for a visitor's request (the product's name…). */
  subject?: string;
}>();

const auth = useAuthStore();
const shop = useShopModulesStore();

const target = computed(() =>
  auth.isAuthenticated
    ? {
        name: 'account',
        query: {
          tab: 'messages',
          new: '1',
          topic: props.topic,
          ...(props.subject ? { subject: props.subject } : {}),
          ...(props.contextType && props.contextId
            ? { context_type: props.contextType, context_id: props.contextId }
            : {}),
        },
      }
    : {
        name: 'contact',
        query: { topic: props.topic, ...(props.subject ? { subject: props.subject } : {}) },
      },
);
</script>

<style scoped lang="scss">
.ask-button {
  padding-left: 0;
  padding-right: 0;
}
</style>
