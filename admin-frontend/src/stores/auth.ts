import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { accessToken, api } from 'src/boot/api';

interface AccessTokenResponse {
  access_token: string;
  expires_in: number;
}

export const useAuthStore = defineStore('auth', () => {
  const loginError = ref<string | null>(null);
  const loggingIn = ref(false);

  const isAuthenticated = computed(() => accessToken.value !== null);

  async function login(email: string, password: string): Promise<boolean> {
    loggingIn.value = true;
    loginError.value = null;
    try {
      const form = new URLSearchParams();
      form.set('username', email);
      form.set('password', password);
      const { data } = await api.post<AccessTokenResponse>('/login/access-token', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      accessToken.value = data.access_token;
      return true;
    } catch (err: unknown) {
      loginError.value = extractErrorMessage(err) ?? 'Échec de connexion';
      return false;
    } finally {
      loggingIn.value = false;
    }
  }

  /**
   * Silently restore the session on app start from the HttpOnly refresh cookie.
   * Safe to call when logged out (it simply leaves the session empty).
   */
  async function tryRestore(): Promise<void> {
    try {
      const { data } = await api.post<AccessTokenResponse>('/login/refresh-token');
      accessToken.value = data.access_token;
    } catch {
      accessToken.value = null;
    }
  }

  async function logout(): Promise<void> {
    // Clear the in-memory token first so the UI reflects logout immediately.
    accessToken.value = null;
    try {
      await api.post('/login/logout');
    } catch {
      // Best effort — the cookie is HttpOnly; server-side revocation may fail
      // offline but the local session is already cleared.
    }
  }

  return {
    isAuthenticated,
    loginError,
    loggingIn,
    login,
    tryRestore,
    logout,
  };
});

function extractErrorMessage(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: unknown } }).response;
    const data = resp?.data;
    if (typeof data === 'object' && data !== null) {
      const errorObj = (data as { error?: { message?: unknown } }).error;
      if (errorObj && typeof errorObj.message === 'string') return errorObj.message;
      const detail = (data as { detail?: unknown }).detail;
      if (typeof detail === 'string') return detail;
      const message = (data as { message?: unknown }).message;
      if (typeof message === 'string') return message;
    }
  }
  return null;
}
