import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { departureCutoffLabel, departureDeliveryLabel } from '@app/utils';
import { getNextDeparture, type Departure } from 'src/api/departures';

/**
 * Next grouped departure (« prochain départ groupé »). Loaded once by the
 * layout; the banner, the product pages and the checkout read the same
 * object, so every surface shows the same dates. `null` = no open departure,
 * the shop behaves as a classic one and nothing is displayed.
 */
export const useDepartureStore = defineStore('departure', () => {
  const next = ref<Departure | null>(null);
  const loaded = ref(false);

  const cutoffLabel = computed(() => (next.value ? departureCutoffLabel(next.value) : null));
  const deliveryLabel = computed(() =>
    next.value ? departureDeliveryLabel(next.value) : null,
  );

  async function load(): Promise<void> {
    try {
      next.value = await getNextDeparture();
    } catch {
      next.value = null;
    } finally {
      loaded.value = true;
    }
  }

  return { next, loaded, cutoffLabel, deliveryLabel, load };
});
