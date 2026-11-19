import { defineStore } from 'pinia';
import { ref } from 'vue';

import { getMessagingInfo, getMyUnreadCount, type MessagingInfo } from '@/api/messaging';

/** Badge interval: a minute is enough for an answer that takes hours. */
const UNREAD_POLL_MS = 60_000;

/**
 * Messaging state shared by the header badge and the « Messages » tab:
 * the unread count (polled while the tab is visible) and the public
 * information (topics, opening hours, response time).
 */
const INFO_TTL_MS = 5 * 60 * 1000;

export const useMessagingStore = defineStore('messaging', () => {
  const unread = ref(0);
  const info = ref<MessagingInfo | null>(null);
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refreshUnread(): Promise<void> {
    try {
      unread.value = await getMyUnreadCount();
    } catch {
      // A failed poll keeps the last count: the badge is a hint.
    }
  }

  function onVisibility(): void {
    if (document.visibilityState === 'visible') void refreshUnread();
  }

  /** Start polling (signed-in customer); idempotent. Browser only. */
  function startPolling(): void {
    if (timer !== null || typeof window === 'undefined') return;
    void refreshUnread();
    timer = setInterval(() => {
      if (document.visibilityState === 'visible') void refreshUnread();
    }, UNREAD_POLL_MS);
    document.addEventListener('visibilitychange', onVisibility);
  }

  function stopPolling(): void {
    if (timer !== null) clearInterval(timer);
    timer = null;
    unread.value = 0;
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibility);
    }
  }

  /**
   * The hours and « open now » change during a visit (review of PR 204: the
   * first answer was kept for the whole session) — read again after a few
   * minutes, the last known answer kept when the call fails.
   */
  let infoAt = 0;
  async function loadInfo(): Promise<MessagingInfo | null> {
    if (info.value && Date.now() - infoAt < INFO_TTL_MS) return info.value;
    try {
      info.value = await getMessagingInfo();
      infoAt = Date.now();
    } catch {
      // Keep what was known: a passing failure does not hide the hours.
    }
    return info.value;
  }

  return { unread, info, refreshUnread, startPolling, stopPolling, loadInfo };
});
