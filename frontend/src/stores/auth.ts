import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { accessToken, api } from 'src/boot/api'

interface AccessTokenResponse {
  access_token: string
  expires_in: number
}

export const useAuthStore = defineStore('auth', () => {
  const loginError = ref<string | null>(null)
  const loggingIn = ref(false)

  const isAuthenticated = computed(() => accessToken.value !== null)

  async function login(email: string, password: string): Promise<boolean> {
    loggingIn.value = true
    loginError.value = null
    try {
      const form = new URLSearchParams()
      form.set('username', email)
      form.set('password', password)
      const { data } = await api.post<AccessTokenResponse>('/login/access-token', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      accessToken.value = data.access_token
      return true
    } catch (err: unknown) {
      loginError.value = extractErrorMessage(err) ?? 'Échec de connexion'
      return false
    } finally {
      loggingIn.value = false
    }
  }

  /**
   * Silently restore the session from the HttpOnly refresh cookie. Used at app
   * startup and right after the OAuth redirect (the cookie is already set).
   * Returns true if a session was restored. Safe to call when logged out.
   */
  async function tryRestore(): Promise<boolean> {
    try {
      const { data } = await api.post<AccessTokenResponse>('/login/refresh-token')
      accessToken.value = data.access_token
      return true
    } catch {
      accessToken.value = null
      return false
    }
  }

  async function logout(): Promise<void> {
    accessToken.value = null
    try {
      await api.post('/login/logout')
    } catch {
      // Best effort — local session already cleared.
    }
  }

  return {
    isAuthenticated,
    loginError,
    loggingIn,
    login,
    tryRestore,
    logout,
  }
})

function extractErrorMessage(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: unknown } }).response
    const data = resp?.data
    if (typeof data === 'object' && data !== null) {
      // Backend AppError shape: { error: { message } }; OAuth2 default: { detail }
      const errorObj = (data as { error?: { message?: unknown } }).error
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message
      const detail = (data as { detail?: unknown }).detail
      if (typeof detail === 'string') return detail
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  }
  return null
}
