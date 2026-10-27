import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';
import { accessToken, api } from '@/boot/api';
import { getMyProfile, type MyProfile } from '@/api/profile';
import { gt } from '@/i18n/global';

interface AccessTokenResponse {
  access_token: string;
  expires_in: number;
}

export const useAuthStore = defineStore('auth', () => {
  const loginError = ref<string | null>(null);
  const loggingIn = ref(false);

  const isAuthenticated = computed(() => accessToken.value !== null);

  /** The signed-in customer, for the header greeting; null while unknown. */
  const profile = ref<MyProfile | null>(null);

  /** First name when known, else the part of the e-mail before the @. */
  const displayName = computed(() => {
    const current = profile.value;
    if (!current) return null;
    const first = current.full_name?.trim().split(/\s+/)[0];
    return first || current.email.split('@')[0] || null;
  });

  function setProfile(next: MyProfile | null) {
    profile.value = next;
  }

  // The access token only lives in the browser (SSR renders signed out): fetch
  // who is signed in once a session appears, forget it when it ends.
  watch(
    accessToken,
    (token, previous) => {
      if (!token) {
        profile.value = null;
      } else if (!previous || !profile.value) {
        void getMyProfile()
          .then((me) => (profile.value = me))
          .catch(() => (profile.value = null));
      }
    },
    { immediate: true },
  );

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
      loginError.value = extractErrorMessage(err) ?? gt('stores.login_failed');
      return false;
    } finally {
      loggingIn.value = false;
    }
  }

  /**
   * Silently restore the session from the HttpOnly refresh cookie. Used at app
   * startup and right after the OAuth redirect (the cookie is already set).
   * Returns true if a session was restored. Safe to call when logged out.
   */
  async function tryRestore(): Promise<boolean> {
    try {
      const { data } = await api.post<AccessTokenResponse>('/login/refresh-token');
      accessToken.value = data.access_token;
      return true;
    } catch {
      accessToken.value = null;
      return false;
    }
  }

  async function logout(): Promise<void> {
    accessToken.value = null;
    try {
      await api.post('/login/logout');
    } catch {
      // Best effort — local session already cleared.
    }
  }

  // --- Email-OTP signup ---------------------------------------------------- //
  interface StepResult {
    ok: boolean;
    error?: string;
  }

  async function sendSignupOtp(
    email: string,
    headers: Record<string, string> = {},
  ): Promise<StepResult> {
    try {
      await api.post('/signup/send-otp', { email }, { headers });
      return { ok: true };
    } catch (err) {
      return { ok: false, error: extractErrorMessage(err) ?? "Impossible d'envoyer le code." };
    }
  }

  async function verifySignupOtp(
    email: string,
    code: string,
  ): Promise<StepResult & { signupToken?: string }> {
    try {
      const { data } = await api.post<{ signup_token: string }>('/signup/verify-otp', {
        email,
        code,
      });
      return { ok: true, signupToken: data.signup_token };
    } catch (err) {
      return { ok: false, error: extractErrorMessage(err) ?? gt('stores.code_invalid') };
    }
  }

  /** Finalise the account and log the user in (sets the in-memory access token). */
  async function completeSignup(
    signupToken: string,
    password: string,
    fullName: string | null,
  ): Promise<StepResult> {
    try {
      const { data } = await api.post<AccessTokenResponse>('/signup/complete', {
        signup_token: signupToken,
        password,
        full_name: fullName,
      });
      accessToken.value = data.access_token;
      return { ok: true };
    } catch (err) {
      return { ok: false, error: extractErrorMessage(err) ?? gt('stores.signup_failed') };
    }
  }

  return {
    isAuthenticated,
    profile,
    displayName,
    setProfile,
    loginError,
    loggingIn,
    login,
    tryRestore,
    logout,
    sendSignupOtp,
    verifySignupOtp,
    completeSignup,
  };
});

function extractErrorMessage(err: unknown): string | null {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const resp = (err as { response?: { data?: unknown } }).response;
    const data = resp?.data;
    if (typeof data === 'object' && data !== null) {
      // Backend AppError shape: { error: { message } }; OAuth2 default: { detail }
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
