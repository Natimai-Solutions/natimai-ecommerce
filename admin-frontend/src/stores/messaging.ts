import { defineStore } from 'pinia';
import { ref } from 'vue';

import { conversationsSummary, type ConversationSummaryCounts } from '@/api/messaging';

const SUMMARY_POLL_MS = 30_000;

/** Counters of the « Messagerie » menu entry and tabs, polled every 30 s
 *  while the back-office tab is visible. */
export const useMessagingStore = defineStore('adminMessaging', () => {
  const summary = ref<ConversationSummaryCounts>({ todo: 0, mine: 0, pending: 0, unread: 0 });
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refresh(): Promise<void> {
    try {
      summary.value = await conversationsSummary();
    } catch {
      // Module off or network: keep the last counters.
    }
  }

  function start(): void {
    if (timer !== null) return;
    void refresh();
    timer = setInterval(() => {
      if (document.visibilityState === 'visible') void refresh();
    }, SUMMARY_POLL_MS);
  }

  function stop(): void {
    if (timer !== null) clearInterval(timer);
    timer = null;
  }

  return { summary, refresh, start, stop };
});
