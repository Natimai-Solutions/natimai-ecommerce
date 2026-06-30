import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { formatMoney } from '@app/utils';
import { getDisplayRates } from 'src/api/currency';
import { updateMyPreferences } from 'src/api/account';
import { useAuthStore } from 'src/stores/auth';

const STORAGE_KEY = 'frontend.display_currency';

/**
 * Display-currency store. Prices are stored/billed in the reference currency
 * (XPF); this converts them for *presentational* display only. The checkout
 * total is always XPF.
 */
export const useCurrencyStore = defineStore('currency', () => {
  const reference = ref('XPF');
  const currency = ref('XPF');
  /** currency_code → rate_to_reference (e.g. USD → 119.0). */
  const rates = ref<Record<string, number>>({});
  const loaded = ref(false);

  const available = computed(() => [reference.value, ...Object.keys(rates.value)]);
  const isConverted = computed(() => currency.value !== reference.value);

  async function loadRates(): Promise<void> {
    try {
      const data = await getDisplayRates();
      reference.value = data.reference_currency;
      rates.value = Object.fromEntries(
        data.rates.map((r) => [r.currency_code, r.rate_to_reference]),
      );
      const stored = localStorage.getItem(STORAGE_KEY);
      currency.value =
        stored && (stored === reference.value || stored in rates.value) ? stored : reference.value;
    } catch {
      // Rates unavailable → stay on the reference currency.
    } finally {
      loaded.value = true;
    }
  }

  /** Convert a reference-currency (XPF) amount to the selected display currency. */
  function convert(amountXpf: number): number {
    if (!isConverted.value) return amountXpf;
    const rate = rates.value[currency.value];
    if (!rate) return amountXpf;
    return amountXpf / rate;
  }

  /** Format a reference-currency (XPF) amount in the selected display currency. */
  function format(amountXpf: number | string): string {
    const n = typeof amountXpf === 'string' ? Number.parseFloat(amountXpf) : amountXpf;
    if (!Number.isFinite(n)) return formatMoney(Number.NaN, currency.value);
    return formatMoney(convert(n), currency.value);
  }

  async function setCurrency(code: string): Promise<void> {
    if (code !== reference.value && !(code in rates.value)) return;
    currency.value = code;
    localStorage.setItem(STORAGE_KEY, code);
    // Persist to the user's profile when logged in (best-effort, non-blocking).
    const auth = useAuthStore();
    if (auth.isAuthenticated) {
      try {
        await updateMyPreferences({ currency_pref: code });
      } catch {
        /* ignore — display preference is also kept in localStorage */
      }
    }
  }

  return {
    reference,
    currency,
    rates,
    loaded,
    available,
    isConverted,
    loadRates,
    convert,
    format,
    setCurrency,
  };
});
