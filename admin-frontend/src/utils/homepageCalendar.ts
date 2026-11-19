/** One change of the homepage: a section starts or ends showing. */
export interface CalendarEvent {
  at: string;
  kind: 'start' | 'end';
  id: string;
  title: string;
  published: boolean;
}

interface Scheduled {
  id: string;
  title: string;
  is_published?: boolean;
  starts_at?: string | null;
  ends_at?: string | null;
}

/**
 * The starts and ends of the next ``days`` days, in time order (lot A4 /
 * R10): what the homepage will look like, change by change. A draft's
 * dates are listed too, marked, since publishing it would make them real.
 */
export function upcomingChanges(
  blocks: Scheduled[],
  now: Date,
  days = 30,
  titleOf: (block: Scheduled) => string = (b) => b.title,
): CalendarEvent[] {
  const from = now.getTime();
  const until = from + days * 86_400_000;
  const events: CalendarEvent[] = [];
  for (const block of blocks) {
    for (const [kind, value] of [
      ['start', block.starts_at],
      ['end', block.ends_at],
    ] as const) {
      if (!value) continue;
      const time = new Date(value).getTime();
      if (Number.isNaN(time) || time < from || time > until) continue;
      events.push({
        at: value,
        kind,
        id: block.id,
        title: titleOf(block),
        published: block.is_published ?? false,
      });
    }
  }
  return events.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
}
