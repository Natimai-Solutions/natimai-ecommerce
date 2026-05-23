import axios from 'axios'
import type { AxiosInstance } from 'axios'

export interface ApiClientOptions {
  baseUrl: string
  getAccessToken?: () => string | null
  setAccessToken?: (token: string) => void
  getRefreshToken?: () => string | null
  clearTokens?: () => void
  onUnauthorized?: () => void
}

export function createApiClient(options: ApiClientOptions): AxiosInstance {
  const client = axios.create({
    baseURL: `${options.baseUrl}/api/v1`,
    headers: { 'Content-Type': 'application/json' },
    timeout: 30_000,
  })

  client.interceptors.request.use((config) => {
    const token = options.getAccessToken?.()
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  client.interceptors.response.use(
    (res) => res,
    async (error) => {
      const originalRequest = error.config as typeof error.config & { _retry?: boolean }

      if (error.response?.status === 401 && !originalRequest._retry) {
        originalRequest._retry = true

        const refreshToken = options.getRefreshToken?.()
        if (refreshToken && options.setAccessToken) {
          try {
            const { data } = await axios.post<{ access_token: string }>(
              `${options.baseUrl}/api/v1/auth/refresh`,
              { refresh_token: refreshToken },
            )
            options.setAccessToken(data.access_token)
            originalRequest.headers.Authorization = `Bearer ${data.access_token}`
            return client(originalRequest)
          } catch {
            options.clearTokens?.()
            options.onUnauthorized?.()
          }
        } else {
          options.onUnauthorized?.()
        }
      }

      return Promise.reject(error)
    },
  )

  return client
}

export type { AxiosInstance }
