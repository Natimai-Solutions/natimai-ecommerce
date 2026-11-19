import { describe, expect, it } from 'vitest';

import { upcomingChanges } from './homepageCalendar';

const now = new Date('2026-11-19T00:00:00Z');

describe('homepage calendar', () => {
  it('lists the starts and ends of the next 30 days in time order', () => {
    const events = upcomingChanges(
      [
        { id: 'a', title: 'Noël', is_published: true, starts_at: '2026-12-10T10:00:00Z', ends_at: '2026-12-26T10:00:00Z' },
        { id: 'b', title: 'Soldes', is_published: false, ends_at: '2026-11-25T10:00:00Z' },
        { id: 'c', title: 'Passé', starts_at: '2026-11-01T00:00:00Z' },
        { id: 'd', title: 'Lointain', starts_at: '2027-03-01T00:00:00Z' },
      ],
      now,
    );
    expect(events.map((e) => `${e.id}:${e.kind}`)).toEqual(['b:end', 'a:start']);
    expect(events[0]?.published).toBe(false);
  });
});
