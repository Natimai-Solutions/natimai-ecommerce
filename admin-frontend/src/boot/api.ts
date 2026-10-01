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

/** Interface language, sent as `Accept-Language` (API messages follow it). */
export const apiLocale = ref<string>('fr');

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
  getAccessToken: () => accessToken.value,
  setAccessToken: (token) => {
    accessToken.value = token;
  },
  clearTokens: () => {
    accessToken.value = null;
  },
  getLocale: () => apiLocale.value,
  onUnauthorized: () => {
    if (typeof window !== 'undefined' && !window.location.hash.includes('/login')) {
      window.location.hash = '#/login';
    }
  },
});

/**
 * Two-factor authentication required and not set up yet: every admin call
 * answers `auth.totp.enrollment_required` — send the person to the one
 * screen they can use, where they enrol.
 */
api.interceptors.response.use(undefined, (error: unknown) => {
  const code = (error as { response?: { data?: { error?: { code?: unknown } } } }).response?.data
    ?.error?.code;
  if (
    code === 'auth.totp.enrollment_required' &&
    typeof window !== 'undefined' &&
    !window.location.hash.includes('/security')
  ) {
    window.location.hash = '#/security';
  }
  return Promise.reject(error instanceof Error ? error : new Error(String(error)));
});

export default defineBoot(() => {
  // api is a singleton — boot exists just to participate in the app lifecycle.
});
