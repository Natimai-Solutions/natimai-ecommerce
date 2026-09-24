<template>
  <q-banner
    v-if="store.next"
    dense
    class="bg-blue-1 text-blue-10 next-departure-banner"
    data-testid="next-departure-banner"
  >
    <template #avatar><q-icon name="event_available" color="primary" /></template>
    <span class="text-weight-medium">Prochain départ groupé « {{ store.next.name }} »</span>
    — {{ store.cutoffLabel }}<template v-if="store.deliveryLabel">
      · {{ store.deliveryLabel }}</template
    >
  </q-banner>
</template>

<script setup lang="ts">
import { useDepartureStore } from 'src/stores/departure';

const store = useDepartureStore();
</script>

<style scoped>
.next-departure-banner {
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
</style>
