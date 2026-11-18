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
  /** The import mode `next` was asked for (null = any). */
  const mode = ref<string | null>(null);

  async function load(serviceLevel: string | null = mode.value): Promise<void> {
    mode.value = serviceLevel;
    try {
      next.value = await getNextDeparture(serviceLevel);
    } catch {
      next.value = null;
    } finally {
      loaded.value = true;
    }
  }

  /**
   * Follow the import mode the customer chose: an order paid by sea joins
   * the next sea departure, not the next air one (functional audit, D1).
   */
  async function setMode(serviceLevel: string | null): Promise<void> {
    if (loaded.value && serviceLevel === mode.value) return;
    await load(serviceLevel);
  }

  return { next, loaded, mode, load, setMode };
});
