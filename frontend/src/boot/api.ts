import { createApiClient } from '@app/api-client'
import type { AxiosInstance } from '@app/api-client'

export const api: AxiosInstance = createApiClient({
  baseUrl: import.meta.env.VITE_API_URL,
})
