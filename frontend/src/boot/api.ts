import { ref } from 'vue'
import { createApiClient } from '@app/api-client'
import type { AxiosInstance } from '@app/api-client'

/**
 * Access token kept in memory only — never localStorage. The refresh token is
 * an HttpOnly cookie (unreadable by JS). The token is set exclusively in the
 * browser (login / OAuth / the startup restore); under SSR this ref stays null,
 * so the server render is always anonymous and no token leaks across requests.
 */
export const accessToken = ref<string | null>(null)

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
  getAccessToken: () => accessToken.value,
  setAccessToken: (token) => {
    accessToken.value = token
  },
  clearTokens: () => {
    accessToken.value = null
  },
})
