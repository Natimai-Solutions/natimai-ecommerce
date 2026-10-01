import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getNextDeparture, type Departure } from '@/api/departures';

/**
 * Next grouped departure (« prochain départ groupé »). Loaded once by the
 * layout; the banner, the product pages and the checkout read the same
 * object, so every surface shows the same dates (labels: useDepartureLabels). `null` = no open departure,
 * the shop behaves as a classic one and nothing is displayed.
 */
export const useDepartureStore = defineStore('departure', () => {
  const next = ref<Departure | null>(null);
  const loaded = ref(false);

  async function load(): Promise<void> {
    try {
      next.value = await getNextDeparture();
    } catch {
      next.value = null;
    } finally {
      loaded.value = true;
    }
  }

  return { next, loaded, load };
});
