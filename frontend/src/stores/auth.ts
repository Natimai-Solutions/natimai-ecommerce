import { defineStore } from 'pinia';
import { computed, ref, watch } from 'vue';
import { accessToken, api } from '@/boot/api';
import { getMyProfile, type MyProfile } from '@/api/profile';
import { gt } from '@/i18n/global';
import { apiErrorCode } from '@/utils/errors';
import { useCartStore } from '@/stores/cart';

interface AccessTokenResponse {
  access_token: string;
  expires_in: number;
}

export const useAuthStore = defineStore('auth', () => {
  const loginError = ref<string | null>(null);
  const loggingIn = ref(false);
  /**
   * The password was accepted and the API now asks for the code of the
   * authenticator app: an administrator with two-factor authentication
   * signing in on the storefront (the API asks it whatever the application).
   */
  const needsSecondFactor = ref(false);

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

  async function login(email: string, password: string, totpCode?: string): Promise<boolean> {
    loggingIn.value = true;
    loginError.value = null;
    try {
      const form = new URLSearchParams();
      form.set('username', email);
      form.set('password', password);
      if (totpCode) form.set('totp_code', totpCode.trim());
      const { data } = await api.post<AccessTokenResponse>('/login/access-token', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      accessToken.value = data.access_token;
      needsSecondFactor.value = false;
      return true;
    } catch (err: unknown) {
      if (apiErrorCode(err) === 'login.totp.required') {
        // Not an error: the password is right, the code is the next step.
        needsSecondFactor.value = true;
        return false;
      }
      loginError.value = extractErrorMessage(err) ?? gt('stores.login_failed');
      return false;
    } finally {
      loggingIn.value = false;
    }
  }

  /** Back to the e-mail and password (another account, or a mistyped one). */
  function resetSecondFactor(): void {
    needsSecondFactor.value = false;
    loginError.value = null;
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
    // The cart of the account stays on the server; this device forgets it.
    useCartStore().forgetLocalCart();
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

  // --- Guest checkout ------------------------------------------------------ //
  /**
   * Order without an account: opens a passwordless account and its session.
   * `reason` tells an address already known: `account` (sign in) or `guest`
   * (an earlier guest order, the take-over link was e-mailed).
   */
  async function startGuestCheckout(
    payload: { email: string; full_name: string; phone: string | null },
    headers: Record<string, string> = {},
  ): Promise<StepResult & { reason?: 'account' | 'guest' }> {
    try {
      const { data } = await api.post<AccessTokenResponse>('/signup/guest', payload, { headers });
      accessToken.value = data.access_token;
      return { ok: true };
    } catch (err) {
      const reason = extractErrorReason(err);
      return {
        ok: false,
        error: extractErrorMessage(err) ?? gt('stores.signup_failed'),
        ...(reason === 'account' || reason === 'guest' ? { reason } : {}),
      };
    }
  }

  return {
    isAuthenticated,
    profile,
    displayName,
    setProfile,
    loginError,
    loggingIn,
    needsSecondFactor,
    login,
    resetSecondFactor,
    tryRestore,
    logout,
    sendSignupOtp,
    verifySignupOtp,
    completeSignup,
    startGuestCheckout,
  };
});

function extractErrorReason(err: unknown): string | null {
  const data = (err as { response?: { data?: { error?: { details?: { reason?: unknown } } } } })
    ?.response?.data;
  const reason = data?.error?.details?.reason;
  return typeof reason === 'string' ? reason : null;
}

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
