import axios from 'axios'
import type { AxiosInstance } from 'axios'

export interface ApiClientOptions {
  baseUrl: string
  /** Returns the in-memory access token (never read from localStorage). */
  getAccessToken?: () => string | null
  /** Stores the access token in memory (called on login and on refresh). */
  setAccessToken?: (token: string) => void
  /** Clears the in-memory access token (called when the session is lost). */
  clearTokens?: () => void
  /** Invoked when an authenticated session could not be refreshed. */
  onUnauthorized?: () => void
  /** Interface language, sent as `Accept-Language` (messages and e-mails follow it). */
  getLocale?: () => string | null
}

export function createApiClient(options: ApiClientOptions): AxiosInstance {
  const client = axios.create({
    baseURL: `${options.baseUrl}/api/v1`,
    headers: { 'Content-Type': 'application/json' },
    timeout: 30_000,
    // Send the HttpOnly refresh cookie on login/refresh/logout (path-scoped).
    withCredentials: true,
  })

  client.interceptors.request.use((config) => {
    const token = options.getAccessToken?.()
    if (token) config.headers.Authorization = `Bearer ${token}`
    const locale = options.getLocale?.()
    if (locale) config.headers['Accept-Language'] = locale
    return config
  })

  // Single-flight refresh: the refresh token is an HttpOnly cookie that the
  // backend rotates on every call (with reuse detection). Concurrent 401s must
  // therefore share one in-flight refresh — otherwise the first rotation
  // invalidates the cookie the others rely on, tripping reuse detection and
  // revoking the whole session.
  let refreshPromise: Promise<string> | null = null

  async function refreshAccessToken(): Promise<string> {
    // Bare axios (not `client`) so this never recurses through the interceptor.
    const { data } = await axios.post<{ access_token: string }>(
      `${options.baseUrl}/api/v1/login/refresh-token`,
      null,
      { withCredentials: true },
    )
    options.setAccessToken?.(data.access_token)
    return data.access_token
  }

  client.interceptors.response.use(
    (res) => res,
    async (error) => {
      const originalRequest = error.config as typeof error.config & { _retry?: boolean }

      // Only try to refresh when an authenticated request (one that carried an
      // access token) comes back 401 — i.e. the token expired. Anonymous 401s
      // are left to the caller (public storefront pages, bootstrap probe…).
      const hadAccessToken = !!options.getAccessToken?.()
      if (
        error.response?.status === 401 &&
        originalRequest &&
        !originalRequest._retry &&
        hadAccessToken
      ) {
        originalRequest._retry = true
        try {
          if (!refreshPromise) {
            refreshPromise = refreshAccessToken().finally(() => {
              refreshPromise = null
            })
          }
          const newToken = await refreshPromise
          originalRequest.headers.Authorization = `Bearer ${newToken}`
          return client(originalRequest)
        } catch {
          options.clearTokens?.()
          options.onUnauthorized?.()
          return Promise.reject(error)
        }
      }

      return Promise.reject(error)
    },
  )

  return client
}

export type { AxiosInstance }
