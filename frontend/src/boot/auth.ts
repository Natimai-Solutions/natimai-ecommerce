import { defineBoot } from '#q-app';
import { useAuthStore } from '@/stores/auth';
import { useCartStore } from '@/stores/cart';

/**
 * Restore the session from the HttpOnly refresh cookie before the app mounts,
 * so authenticated pages see the correct state on their first render.
 *
 * Client-only: the SSR server render has no browser cookie and stays anonymous;
 * the access token therefore never exists server-side.
 */
export default defineBoot(async () => {
  if (import.meta.env.QUASAR_CLIENT) {
    const restored = await useAuthStore().tryRestore();
    // A guest cart left from a signed-out visit joins the account's (R8 / U9).
    if (restored) void useCartStore().mergeAfterLogin();
  }
});
