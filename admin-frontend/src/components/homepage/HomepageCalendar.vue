<template>
  <section class="homepage-calendar" data-testid="homepage-calendar">
    <h2 class="admin-subtitle">{{ $t('homepage.calendar_title') }}</h2>
    <p v-if="!events.length" class="admin-hint">{{ $t('homepage.calendar_empty') }}</p>
    <q-list v-else bordered separator dense class="rounded-borders">
      <q-item v-for="event in events" :key="`${event.id}-${event.kind}`">
        <q-item-section avatar>
          <q-icon :name="event.kind === 'start' ? 'ph:play-circle' : 'ph:stop-circle'" />
        </q-item-section>
        <q-item-section>
          <q-item-label>
            {{
              event.kind === 'start'
                ? $t('homepage.calendar_start', { title: event.title })
                : $t('homepage.calendar_end', { title: event.title })
            }}
          </q-item-label>
          <q-item-label caption>
            {{ formatDateTime(event.at) }}
            <template v-if="!event.published"> · {{ $t('homepage.calendar_draft') }}</template>
          </q-item-label>
        </q-item-section>
      </q-item>
    </q-list>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { formatDateTime } from '@app/utils';

import type { HomepageBlock } from '@/api/homepage';
import { upcomingChanges } from '@/utils/homepageCalendar';

const props = defineProps<{
  blocks: HomepageBlock[];
  titleOf: (block: HomepageBlock) => string;
}>();

const events = computed(() =>
  upcomingChanges(props.blocks, new Date(), 30, (b) => props.titleOf(b as HomepageBlock)),
);
</script>

<style scoped lang="scss">
.homepage-calendar {
  margin-top: 32px;
}
</style>
