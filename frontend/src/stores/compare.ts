import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

/** Up to four products side by side: more than that no longer compares. */
export const COMPARE_MAX = 4;
const STORAGE_KEY = 'natimai:compare';

function readStored(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((id): id is string => typeof id === 'string').slice(0, COMPARE_MAX)
      : [];
  } catch {
    return [];
  }
}

function writeStored(ids: string[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Private mode or full storage: the shortlist lives for the session only.
  }
}

/**
 * The visitor's comparison shortlist (R8 / confort), kept in the browser:
 * no account needed, nothing to persist server side. Hydrated on the client
 * only (`load()` from the layout), so the SSR markup never depends on it.
 */
export const useCompareStore = defineStore('compare', () => {
  const ids = ref<string[]>([]);
  const loaded = ref(false);

  const count = computed(() => ids.value.length);
  const isFull = computed(() => ids.value.length >= COMPARE_MAX);

  function load() {
    if (loaded.value) return;
    ids.value = readStored();
    loaded.value = true;
  }

  function has(productId: string): boolean {
    return ids.value.includes(productId);
  }

  /** Adds the product; false when the shortlist is full. */
  function add(productId: string): boolean {
    if (has(productId)) return true;
    if (isFull.value) return false;
    ids.value = [...ids.value, productId];
    writeStored(ids.value);
    return true;
  }

  function remove(productId: string) {
    if (!has(productId)) return;
    ids.value = ids.value.filter((id) => id !== productId);
    writeStored(ids.value);
  }

  /** Toggles the product; false when it could not be added (shortlist full). */
  function toggle(productId: string): boolean {
    if (has(productId)) {
      remove(productId);
      return true;
    }
    return add(productId);
  }

  function clear() {
    ids.value = [];
    writeStored(ids.value);
  }

  return { ids, count, isFull, loaded, load, has, add, remove, toggle, clear };
});
