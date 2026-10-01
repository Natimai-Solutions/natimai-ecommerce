<template>
  <section class="app-section">
    <div class="app-section__head">
      <h2 class="app-section__title">{{ $t('quotes.title') }}</h2>
      <p class="app-section__hint">
        {{ $t('quotes.hint') }}
      </p>
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <ul v-if="loading" class="app-rows" aria-busy="true">
      <li v-for="n in 2" :key="n" class="app-row">
        <div class="app-row__main">
          <q-skeleton type="text" width="30%" />
          <q-skeleton type="text" width="50%" />
        </div>
      </li>
    </ul>

    <div v-else-if="!quotes.length" class="app-empty">
      <q-icon name="ph:file-text" size="36px" class="text-subtle" />
      <h3>{{ $t('quotes.none') }}</h3>
      <p>{{ $t('quotes.none_text') }}</p>
      <q-btn outline color="primary" :label="$t('quotes.to_cart')" :to="{ name: 'cart' }" />
    </div>

    <ul v-else class="app-rows" data-testid="account-quotes">
      <li v-for="quote in quotes" :key="quote.id" class="app-row">
        <div class="app-row__main">
          <span class="app-row__title">
            <span v-if="quote.quote_number" class="font-mono">{{ quote.quote_number }}</span>
            <template v-else>{{ $t('quotes.request') }}</template>
          </span>
          <span class="app-row__meta">
            {{ formatDate(quote.quoted_at ?? quote.created_at) }}
            <template v-if="quote.valid_until">
              {{ $t('quotes.valid_until', { date: formatDate(quote.valid_until) }) }}
            </template>
          </span>
          <span class="quote__tags">
            <StatusTag
              :tone="quote.status === 'won' ? 'ok' : quote.status === 'quoted' ? 'warn' : 'neutral'"
              :label="quoteStatusLabel(quote.status)"
            />
          </span>
        </div>
        <div class="app-row__side quote__side">
          <span v-if="quote.total_amount" class="font-mono quote__total">
            {{ orderMoney(quote.total_amount, quote.currency, currencyStore.reference) }}
          </span>
          <button
            v-if="quote.quote_number"
            type="button"
            class="text-link"
            @click="onDownload(quote)"
          >
            PDF
          </button>
          <q-btn
            v-if="quote.can_order"
            unelevated
            color="primary"
            :label="$t('quotes.order')"
            :loading="orderingId === quote.id"
            data-testid="account-order-quote"
            @click="onOrder(quote)"
          />
          <q-btn
            v-else-if="quote.order_id"
            outline
            color="primary"
            :label="$t('quotes.see_order')"
            :to="{ name: 'order-tracking', params: { id: quote.order_id } }"
          />
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { formatDate } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { acceptMyQuote, downloadMyQuotePdf, listMyQuotes, type MyQuote } from '@/api/quotes';
import { useCartStore } from '@/stores/cart';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';
import { orderMoney } from '@/utils/money';

const i18n = useI18n();
const t = i18n.t;
const te = (key: string) => i18n.te(key);

function quoteStatusLabel(status: string): string {
  return te(`quotes.status.${status}`) ? t(`quotes.status.${status}`) : status;
}

const router = useRouter();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();

const quotes = ref<MyQuote[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const orderingId = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    quotes.value = await listMyQuotes();
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('quotes.load_failed');
  } finally {
    loading.value = false;
  }
}

async function onDownload(quote: MyQuote) {
  error.value = null;
  try {
    await downloadMyQuotePdf(quote);
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('quotes.pdf_failed');
  }
}

/** Le panier serveur est rechargé depuis le devis ; le panier local le suit,
 * et le checkout passe en mode devis (`?quote=`) pour appliquer ses prix. */
async function onOrder(quote: MyQuote) {
  orderingId.value = quote.id;
  error.value = null;
  try {
    const cart = await acceptMyQuote(quote.id);
    const items = cart.items ?? [];
    cartStore.clearCart();
    for (const item of items) {
      await cartStore.addItem(item.product_id, item.quantity);
    }
    cartStore.applyServerPrices(
      items.map((item) => ({
        product_id: item.product_id,
        current_unit_price: String(item.unit_price),
      })),
    );
    await router.push({ name: 'checkout', query: { quote: quote.id } });
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('quotes.order_failed');
  } finally {
    orderingId.value = null;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.quote__tags {
  margin-top: 6px;
}

.quote__side {
  flex-wrap: wrap;
  justify-content: flex-end;

  @media (max-width: 599px) {
    width: 100%;
    justify-content: space-between;
  }
}

.quote__total {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}
</style>
