import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

const { getMessagingInfo } = vi.hoisted(() => ({ getMessagingInfo: vi.fn() }));
vi.mock('@/api/messaging', () => ({ getMessagingInfo, getMyUnreadCount: vi.fn() }));

import { useMessagingStore } from './messaging';

describe('messaging hours (review of PR 204)', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getMessagingInfo.mockReset();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('reads the hours again after a few minutes, keeping them on a failure', async () => {
    getMessagingInfo.mockResolvedValueOnce({ open_now: true });
    const store = useMessagingStore();
    await store.loadInfo();
    await store.loadInfo();
    expect(getMessagingInfo).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(6 * 60 * 1000);
    getMessagingInfo.mockRejectedValueOnce(new Error('offline'));
    expect(await store.loadInfo()).toEqual({ open_now: true });

    getMessagingInfo.mockResolvedValueOnce({ open_now: false });
    expect(await store.loadInfo()).toEqual({ open_now: false });
  });
});
