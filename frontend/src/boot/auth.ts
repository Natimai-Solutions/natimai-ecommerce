import { defineBoot } from '#q-app/wrappers';
import { useAuthStore } from 'src/stores/auth';

/**
 * Restore the session from the HttpOnly refresh cookie before the app mounts,
 * so authenticated pages see the correct state on their first render.
 *
 * Client-only: the SSR server render has no browser cookie and stays anonymous;
 * the access token therefore never exists server-side.
 */
export default defineBoot(async () => {
  if (process.env.CLIENT) {
    await useAuthStore().tryRestore();
  }
});
