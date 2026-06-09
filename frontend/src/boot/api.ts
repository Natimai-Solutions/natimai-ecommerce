import { createApiClient } from '@app/api-client'
import type { AxiosInstance } from '@app/api-client'

const ACCESS_KEYS = ['frontend.access_token', 'admin.access_token']
const REFRESH_KEYS = ['frontend.refresh_token', 'admin.refresh_token']

function getFromStorage(keys: string[]): string | null {
  if (typeof window === 'undefined') return null
  for (const key of keys) {
    const token = localStorage.getItem(key)
    if (token) return token
  }
  return null
}

export function hasAuthToken(): boolean {
  return getFromStorage(ACCESS_KEYS) !== null
}

const ACCESS_KEY = 'frontend.access_token'
const REFRESH_KEY = 'frontend.refresh_token'

/** Storefront token storage (scoped to the `frontend.*` keys). */
export const tokenStorage = {
  getAccess(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(ACCESS_KEY)
  },
  setAccess(token: string): void {
    if (typeof window === 'undefined') return
    localStorage.setItem(ACCESS_KEY, token)
  },
  getRefresh(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(REFRESH_KEY)
  },
  setRefresh(token: string): void {
    if (typeof window === 'undefined') return
    localStorage.setItem(REFRESH_KEY, token)
  },
  clear(): void {
    if (typeof window === 'undefined') return
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
  getAccessToken: () => getFromStorage(ACCESS_KEYS),
  setAccessToken: (token) => {
    if (typeof window === 'undefined') return
    localStorage.setItem('frontend.access_token', token)
  },
  getRefreshToken: () => getFromStorage(REFRESH_KEYS),
  clearTokens: () => {
    if (typeof window === 'undefined') return
    localStorage.removeItem('frontend.access_token')
    localStorage.removeItem('frontend.refresh_token')
  },
})
