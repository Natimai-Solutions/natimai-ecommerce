import { defineStore } from 'pinia';
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
  /** Read in the browser after mount: the server render cannot know it. */
  const dismissed = ref<string | null>(null);

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

  function readDismissed(): void {
    try {
      dismissed.value = window.localStorage.getItem(DISMISSED_KEY);
    } catch {
      dismissed.value = null;
    }
  }

  function dismiss(): void {
    if (!current.value) return;
    const key = announcementKey(current.value);
    dismissed.value = key;
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

  return { current, loaded, dismissed, load, readDismissed, dismiss, showPreview };
});
