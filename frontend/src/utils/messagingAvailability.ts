import type { MessagingInfo } from '@/api/messaging';

type Translate = (key: string, ...args: unknown[]) => string;

/**
 * « We answer Monday to Friday, 8:00–17:00 (Tahiti time), usually within
 * 24 h. » and, outside the hours (§6 of the chantier), « We will answer
 * from Monday 8:00. » — the day and time come from the server, in the
 * shop's zone: no date arithmetic here (Tahiti, UTC-10).
 */
export function messagingAvailability(info: MessagingInfo | null, t: Translate): string {
  if (!info) return '';
  const days =
    info.days.join(',') === '1,2,3,4,5'
      ? t('messaging.weekdays')
      : info.days.map((d) => t(`messaging.day.${d}`)).join(', ');
  const delay =
    info.response_time.unit === 'business_days'
      ? t('messaging.delay_days', info.response_time.value)
      : t('messaging.delay_hours', { n: info.response_time.value });
  const text = t('messaging.availability', {
    days,
    start: info.hours_start,
    end: info.hours_end,
    delay,
  });
  if (info.open_now !== false || !info.next_opening) return text;
  const [date, time] = info.next_opening.split('T');
  const offset = info.next_opening_days ?? 2;
  let when: string;
  if (offset === 0) when = t('messaging.today');
  else if (offset === 1) when = t('messaging.tomorrow');
  else {
    // The weekday of a pure date, without the browser's time zone.
    const [y, m, d] = (date ?? '').split('-').map(Number);
    const weekday = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1)).getUTCDay() || 7;
    when = t(`messaging.day.${weekday}`);
  }
  return `${text} ${t('messaging.next_opening', { when, time })}`;
}
