import { ref } from 'vue';
import { createApiClient } from '@app/api-client';
import type { AxiosInstance } from '@app/api-client';

import { currentRequestScope } from '@/ssr/requestScope';

/**
 * Access token kept in memory only — never localStorage. The refresh token is
 * an HttpOnly cookie (unreadable by JS). The token is set exclusively in the
 * browser (login / OAuth / the startup restore); under SSR this ref stays null,
 * so the server render is always anonymous and no token leaks across requests.
 */
export const accessToken = ref<string | null>(null);

/** Interface language sent with every call (set by the i18n boot and switcher). */
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
  // Server render: this request's language, not the last one set (F1).
  getLocale: () => currentRequestScope()?.locale ?? apiLocale.value,
});
