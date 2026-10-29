import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { ref } from 'vue';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/boot/api', () => ({ accessToken: ref<string | null>(null), api: { post } }));
vi.mock('@/api/profile', () => ({ getMyProfile: vi.fn(() => Promise.reject(new Error('n/a'))) }));
vi.mock('@/i18n/global', () => ({ gt: (key: string) => key }));

import { useAuthStore } from './auth';

function apiError(code: string, message: string, status = 401) {
  return Object.assign(new Error(message), {
    response: { status, data: { error: { code, message, details: {} } } },
  });
}

describe('storefront sign-in with a second factor', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    post.mockReset();
  });

  it('asks for the authenticator code instead of showing an error', async () => {
    post.mockRejectedValueOnce(
      apiError('login.totp.required', "Saisissez le code de votre application d'authentification."),
    );
    const store = useAuthStore();

    expect(await store.login('admin@example.com', 'secret')).toBe(false);
    expect(store.needsSecondFactor).toBe(true);
    expect(store.loginError).toBeNull();
    const [, form] = post.mock.calls[0] as [string, URLSearchParams];
    expect(form.has('totp_code')).toBe(false);
  });

  it('sends the code with the password and opens the session', async () => {
    post.mockRejectedValueOnce(apiError('login.totp.required', 'code ?'));
    post.mockResolvedValueOnce({ data: { access_token: 'jwt', expires_in: 900 } });
    const store = useAuthStore();
    await store.login('admin@example.com', 'secret');

    expect(await store.login('admin@example.com', 'secret', ' 123456 ')).toBe(true);
    expect(store.needsSecondFactor).toBe(false);
    const [, form] = post.mock.calls[1] as [string, URLSearchParams];
    expect(form.get('totp_code')).toBe('123456');
    expect(form.get('username')).toBe('admin@example.com');
  });

  it('a wrong code is an ordinary error and the code is asked again', async () => {
    post.mockRejectedValueOnce(apiError('login.totp.required', 'code ?'));
    post.mockRejectedValueOnce(apiError('login.totp.invalid', 'Code de vérification incorrect.'));
    const store = useAuthStore();
    await store.login('admin@example.com', 'secret');

    expect(await store.login('admin@example.com', 'secret', '000000')).toBe(false);
    expect(store.needsSecondFactor).toBe(true);
    expect(store.loginError).toBe('Code de vérification incorrect.');

    store.resetSecondFactor();
    expect(store.needsSecondFactor).toBe(false);
    expect(store.loginError).toBeNull();
  });

  it('a wrong password stays a plain error', async () => {
    post.mockRejectedValueOnce(
      apiError('login.credentials.invalid', 'Email ou mot de passe incorrect.', 400),
    );
    const store = useAuthStore();

    expect(await store.login('client@example.com', 'nope')).toBe(false);
    expect(store.needsSecondFactor).toBe(false);
    expect(store.loginError).toBe('Email ou mot de passe incorrect.');
  });
});
