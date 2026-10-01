import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { formatMoney, setCurrencyDecimals } from '@app/utils';
import { getDisplayRates } from '@/api/currency';
import { updateMyPreferences } from '@/api/account';
import { useAuthStore } from '@/stores/auth';
import { useShopModulesStore } from '@/stores/shopModules';

const STORAGE_KEY = 'frontend.display_currency';

/**
 * Display-currency store. Prices are stored/billed in the reference currency;
 * this converts them for *presentational* display only. The checkout total is
 * always in the reference currency. A visitor who chose nothing sees the
 * shop's default display currency (Admin → Paramètres → Affichage).
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
      const decimals: Record<string, number> = {};
      if (data.reference_decimals !== undefined) {
        decimals[data.reference_currency] = data.reference_decimals;
      }
      for (const r of data.rates)
        if (r.decimals !== undefined) decimals[r.currency_code] = r.decimals;
      setCurrencyDecimals(decimals);

      const known = (code: string | null | undefined): code is string =>
        !!code && (code === reference.value || code in rates.value);
      let stored: string | null = null;
      try {
        stored = localStorage.getItem(STORAGE_KEY);
      } catch {
        stored = null;
      }
      const shop = useShopModulesStore();
      await shop.load();
      const shopDefault = shop.config.default_display_currency;
      currency.value = known(stored) ? stored : known(shopDefault) ? shopDefault : reference.value;
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
