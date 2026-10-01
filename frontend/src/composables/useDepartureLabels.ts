import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { departureDaysLeft, formatDate, type DepartureLike } from '@app/utils';

import { useDepartureStore } from '@/stores/departure';

/** Labels of grouped departures, in the visitor's language. */
export function useDepartureLabels() {
  const i18n = useI18n();
  const t = i18n.t;
  const te = (key: string) => i18n.te(key);
  const store = useDepartureStore();

  function cutoffLabel(d: DepartureLike, now: Date = new Date()): string {
    const date = formatDate(d.order_cutoff_at);
    const days = departureDaysLeft(d, now);
    if (days < 0) return t('departure.cutoff', { date });
    if (days === 0) return t('departure.cutoff_last_day', { date });
    return t('departure.cutoff_days', { date, n: days }, days);
  }

  function deliveryLabel(d: DepartureLike): string | null {
    if (!d.estimated_delivery_at) return null;
    return t('departure.delivery', { date: formatDate(d.estimated_delivery_at) });
  }

  function statusLabel(status: string): string {
    const key = `departure.status.${status}`;
    return te(key) ? t(key) : status;
  }

  const nextCutoff = computed(() => (store.next ? cutoffLabel(store.next) : null));
  const nextDelivery = computed(() => (store.next ? deliveryLabel(store.next) : null));

  return { cutoffLabel, deliveryLabel, statusLabel, nextCutoff, nextDelivery };
}
