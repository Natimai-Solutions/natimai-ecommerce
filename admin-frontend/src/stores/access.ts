import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getMe, type Me } from '@/api/me';

/** Who is signed in to the back-office and what they may open (lot ROLE). */
export const useAccessStore = defineStore('access', () => {
  const me = ref<Me | null>(null);
  let pending: Promise<Me | null> | null = null;

  function load(force = false): Promise<Me | null> {
    if (me.value && !force) return Promise.resolve(me.value);
    pending ??= getMe()
      .then((data) => (me.value = data))
      .catch(() => (me.value = null))
      .finally(() => (pending = null));
    return pending;
  }

  function reset(): void {
    me.value = null;
  }

  return { me, load, reset };
});
