import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, tokenStorage } from 'src/boot/api'

interface TokenResponse {
  access_token: string
  refresh_token: string
  expires_in: number
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(tokenStorage.getAccess())
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
      const { data } = await api.post<TokenResponse>('/login/access-token', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      tokenStorage.setAccess(data.access_token)
      tokenStorage.setRefresh(data.refresh_token)
      accessToken.value = data.access_token
      return true
    } catch (err: unknown) {
      const message = extractErrorMessage(err)
      loginError.value = message ?? 'Échec de connexion'
      return false
    } finally {
      loggingIn.value = false
    }
  }

  function logout() {
    tokenStorage.clear()
    accessToken.value = null
  }

  return {
    accessToken,
    isAuthenticated,
    loginError,
    loggingIn,
    login,
    logout,
  }
})

function extractErrorMessage(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: unknown } }).response
    const data = resp?.data
    if (typeof data === 'object' && data !== null) {
      const detail = (data as { detail?: unknown; message?: unknown }).detail
      if (typeof detail === 'string') return detail
      const message = (data as { message?: unknown }).message
      if (typeof message === 'string') return message
    }
  }
  return null
}
