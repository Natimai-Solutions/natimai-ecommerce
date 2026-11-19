import { describe, expect, it } from 'vitest';

import type { MessagingInfo } from '@/api/messaging';

import { messagingAvailability } from './messagingAvailability';

const t = (key: string, ...args: unknown[]) => `${key}${args.length ? JSON.stringify(args[0]) : ''}`;

const base = {
  channels: [],
  hours_start: '08:00',
  hours_end: '17:00',
  days: [1, 2, 3, 4, 5],
  timezone: 'Pacific/Tahiti',
  response_time: { unit: 'hours', value: 24, measured: false },
} as unknown as MessagingInfo;

describe('messaging availability', () => {
  it('says nothing more while the team is at work', () => {
    expect(messagingAvailability({ ...base, open_now: true }, t)).not.toContain('next_opening');
  });

  it('names the day the team is back, from the pure date', () => {
    const text = messagingAvailability(
      { ...base, open_now: false, next_opening: '2026-11-23T08:00', next_opening_days: 2 },
      t,
    );
    // 23/11/2026 is a Monday, whatever the browser's zone.
    expect(text).toContain('messaging.next_opening{"when":"messaging.day.1","time":"08:00"}');
  });

  it('says tomorrow and today', () => {
    const tomorrow = { ...base, open_now: false, next_opening: '2026-11-24T08:00' };
    expect(messagingAvailability({ ...tomorrow, next_opening_days: 1 }, t)).toContain(
      'messaging.tomorrow',
    );
    expect(messagingAvailability({ ...tomorrow, next_opening_days: 0 }, t)).toContain(
      'messaging.today',
    );
  });
});
