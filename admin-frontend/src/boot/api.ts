import { defineBoot } from '#q-app/wrappers'
import { createApiClient } from '@app/api-client'
import type { AxiosInstance } from '@app/api-client'

const ACCESS_KEY = 'admin.access_token'
const REFRESH_KEY = 'admin.refresh_token'

export const tokenStorage = {
  getAccess: (): string | null => localStorage.getItem(ACCESS_KEY),
  setAccess: (token: string) => localStorage.setItem(ACCESS_KEY, token),
  getRefresh: (): string | null => localStorage.getItem(REFRESH_KEY),
  setRefresh: (token: string) => localStorage.setItem(REFRESH_KEY, token),
  clear: () => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
  getAccessToken: tokenStorage.getAccess,
  setAccessToken: tokenStorage.setAccess,
  getRefreshToken: tokenStorage.getRefresh,
  clearTokens: tokenStorage.clear,
  onUnauthorized: () => {
    if (typeof window !== 'undefined' && !window.location.hash.includes('/login')) {
      window.location.hash = '#/login'
    }
  },
})

export default defineBoot(() => {
  // api is a singleton — boot exists just to participate in app lifecycle
})
