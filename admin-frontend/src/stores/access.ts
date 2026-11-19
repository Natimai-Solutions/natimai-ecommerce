import { defineStore } from 'pinia';
import { ref, watch } from 'vue';

import { accessToken } from '@/boot/api';

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

  // Signed out (or the session ended: a role change rotates the security
  // stamp, the refresh fails and clears the token): the rights are read
  // again at the next sign-in. A silent refresh of the token keeps them.
  watch(accessToken, (token) => {
    if (token === null) reset();
  });

  return { me, load, reset };
});
