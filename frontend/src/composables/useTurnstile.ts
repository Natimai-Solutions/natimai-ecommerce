import { computed, onBeforeUnmount, ref } from 'vue';

import { useShopModulesStore } from '@/stores/shopModules';

/** The Cloudflare Turnstile script, loaded once per page. */
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

/** Header carrying the token to the API (`app.core.captcha.TOKEN_HEADER`). */
export const CAPTCHA_HEADER = 'X-Captcha-Token';

interface TurnstileApi {
  render(
    container: HTMLElement,
    options: {
      sitekey: string;
      theme?: 'light' | 'dark' | 'auto';
      language?: string | undefined;
      callback?: (token: string) => void;
      'expired-callback'?: () => void;
      'error-callback'?: () => void;
    },
  ): string;
  reset(widgetId: string): void;
  remove(widgetId: string): void;
}

declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

let scriptPromise: Promise<TurnstileApi> | null = null;

function loadScript(): Promise<TurnstileApi> {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'));
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise<TurnstileApi>((resolve, reject) => {
      const script = document.createElement('script');
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.onload = () => {
        if (window.turnstile) resolve(window.turnstile);
        else reject(new Error('Turnstile did not load'));
      };
      script.onerror = () => {
        scriptPromise = null;
        reject(new Error('Turnstile script failed'));
      };
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
}

/**
 * Cloudflare Turnstile on a public form (R8 / U5).
 *
 * Active only when the shop configured a site key (`GET /system/config`):
 * then `enabled` is true, the form must mount the widget (`mount`) and send
 * `headers()` with its request. Tokens are single-use: call `reset()` after
 * each submission. Without a site key everything is inert and `headers()`
 * is empty — the API then checks nothing either.
 */
export function useTurnstile() {
  const shop = useShopModulesStore();
  const siteKey = computed(() => shop.config.captcha_site_key ?? null);
  const enabled = computed(() => Boolean(siteKey.value));
  const token = ref<string | null>(null);
  const failed = ref(false);
  let widgetId: string | null = null;
  let api: TurnstileApi | null = null;

  /** True when the form may be submitted (no captcha, or a token in hand). */
  const ready = computed(() => !enabled.value || token.value !== null || failed.value);

  async function mount(container: HTMLElement | null, language?: string): Promise<void> {
    if (!container || !siteKey.value) return;
    try {
      api = await loadScript();
    } catch {
      // The script is blocked or Cloudflare is down: the API fails open on
      // its side too, the rate limits still stand.
      failed.value = true;
      return;
    }
    if (widgetId) api.remove(widgetId);
    widgetId = api.render(container, {
      sitekey: siteKey.value,
      theme: 'light',
      language,
      callback: (value) => {
        token.value = value;
      },
      'expired-callback': () => {
        token.value = null;
      },
      'error-callback': () => {
        failed.value = true;
      },
    });
  }

  function reset(): void {
    token.value = null;
    if (api && widgetId) api.reset(widgetId);
  }

  /** Request headers for the submission; empty when no captcha applies. */
  function headers(): Record<string, string> {
    return token.value ? { [CAPTCHA_HEADER]: token.value } : {};
  }

  onBeforeUnmount(() => {
    if (api && widgetId) api.remove(widgetId);
    widgetId = null;
  });

  return { enabled, ready, token, mount, reset, headers };
}
