import { defineBoot } from '#q-app';
import { ref } from 'vue';
import { createApiClient } from '@app/api-client';
import type { AxiosInstance } from '@app/api-client';

/**
 * Access token kept in memory only — never localStorage. An XSS payload can't
 * dump it from storage, and it disappears on reload (restored via the refresh
 * cookie at startup). The refresh token itself is an HttpOnly cookie the browser
 * sends automatically to /login/* — unreadable by JS.
 */
export const accessToken = ref<string | null>(null);

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
  getAccessToken: () => accessToken.value,
  setAccessToken: (token) => {
    accessToken.value = token;
  },
  clearTokens: () => {
    accessToken.value = null;
  },
  onUnauthorized: () => {
    if (typeof window !== 'undefined' && !window.location.hash.includes('/login')) {
      window.location.hash = '#/login';
    }
  },
});

export default defineBoot(() => {
  // api is a singleton — boot exists just to participate in the app lifecycle.
});
