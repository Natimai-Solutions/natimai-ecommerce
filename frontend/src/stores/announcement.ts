import { defineStore } from 'pinia';
import { Cookies } from 'quasar';
import { ref } from 'vue';

import { getAnnouncement } from '@/api/homepage';
import type { HomepageSection } from '@/api/homepage';

const DISMISSED_KEY = 'announcement-dismissed';

/** What identifies an announcement as read: its id and its text, so that an
 *  edited announcement shows again. */
export function announcementKey(item: Pick<HomepageSection, 'id' | 'title'>): string {
  let hash = 0;
  for (const ch of item.title) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return `${item.id}:${hash}`;
}

/**
 * The shop's announcement above the header of every page (lot A3 / R4).
 * Loaded by the layout during the server render; closed by the visitor,
 * remembered in this browser only.
 */
export const useAnnouncementStore = defineStore('announcement', () => {
  const current = ref<HomepageSection | null>(null);
  const loaded = ref(false);
  const loadedLocale = ref<string | null>(null);
  /**
   * The announcement this visitor closed. Kept in a cookie (a preference,
   * nothing tracked) so that the server render already leaves it out: read
   * from localStorage only, it showed for a moment on every page load.
   */
  const dismissed = ref<string | null>(null);

  /** Server render: the visitor's choice, from the request's cookies. */
  function readFromCookies(cookies: { get: (name: string) => string | null | undefined }): void {
    dismissed.value = cookies.get(DISMISSED_KEY) ?? null;
  }

  async function load(locale: string): Promise<void> {
    if (loaded.value && loadedLocale.value === locale) return;
    try {
      current.value = await getAnnouncement();
    } catch {
      current.value = null;
    } finally {
      loaded.value = true;
      loadedLocale.value = locale;
    }
  }

  /** In the browser: the cookie, else a choice made before it existed. */
  function readDismissed(): void {
    const fromCookie = Cookies.get(DISMISSED_KEY);
    if (fromCookie) {
      dismissed.value = fromCookie;
      return;
    }
    try {
      dismissed.value = window.localStorage.getItem(DISMISSED_KEY);
    } catch {
      dismissed.value = null;
    }
    if (dismissed.value) remember(dismissed.value);
  }

  function remember(key: string): void {
    Cookies.set(DISMISSED_KEY, key, {
      path: '/',
      expires: 365,
      sameSite: 'Lax',
      secure: window.location.protocol === 'https:',
    });
  }

  function dismiss(): void {
    if (!current.value) return;
    const key = announcementKey(current.value);
    dismissed.value = key;
    remember(key);
    try {
      window.localStorage.setItem(DISMISSED_KEY, key);
    } catch {
      // Private window: closed for this visit only.
    }
  }

  /** The admin's preview: the announcement of the simulated date, shown
   *  even if this browser closed it. */
  function showPreview(item: HomepageSection | null): void {
    current.value = item;
    loaded.value = true;
    loadedLocale.value = null;
    dismissed.value = null;
  }

  return {
    current,
    loaded,
    dismissed,
    load,
    readFromCookies,
    readDismissed,
    dismiss,
    showPreview,
  };
});
