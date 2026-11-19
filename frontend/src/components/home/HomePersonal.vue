<template>
  <section
    v-if="source === 'current_order' ? !!order : products.length"
    class="home-section page-container"
    :aria-labelledby="`home-section-${section.id}`"
    :data-testid="`home-personal-${source}`"
  >
    <div class="home-section__head">
      <h2 :id="`home-section-${section.id}`" class="home-section__title">
        {{ section.title || $t(`home.personal_${source}`) }}
      </h2>
    </div>

    <router-link
      v-if="order"
      :to="`/mon-compte/commandes/${order.id}`"
      class="current-order"
      data-testid="home-current-order"
    >
      <q-icon name="ph:package" size="28px" class="current-order__icon" />
      <span class="current-order__body">
        <span class="current-order__number">
          {{ $t('home.order_number', { number: order.order_number || '—' }) }}
        </span>
        <span class="current-order__meta">
          {{ orderStatusLabel(order.status, t) }} ·
          {{ currency.format(order.total_amount) }}
        </span>
      </span>
      <span class="current-order__link">{{ $t('home.order_follow') }}</span>
      <q-icon name="ph:caret-right" size="16px" />
    </router-link>

    <div v-else class="product-grid">
      <ProductCard
        v-for="product in products"
        :key="product.id"
        :product="product"
        @add-to-cart="emit('add-to-cart', $event)"
        @compare-full="emit('compare-full')"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { components } from '@app/api-types';

import ProductCard from '@/components/ProductCard.vue';
import type { HomepageSection } from '@/api/homepage';
import { getProductsByIds } from '@/api/products';
import { useCurrencyStore } from '@/stores/currency';
import { orderStatusLabel } from '@/utils/orderStatus';
import { readRecentlyViewed } from '@/utils/recentlyViewed';

type ProductPublic = components['schemas']['ProductPublic'];

const props = defineProps<{ section: HomepageSection }>();
const emit = defineEmits<{ 'add-to-cart': [product: ProductPublic]; 'compare-full': [] }>();
const { t } = useI18n();
const currency = useCurrencyStore();

const source = computed(() => {
  const value = props.section.config?.['source'];
  return typeof value === 'string' ? value : 'recently_viewed';
});
const limit = computed(() => Number(props.section.config?.['limit'] ?? 8));
const order = computed(() => props.section.current_order ?? null);
/** Read in the browser after mount: the server render never has it. */
const viewed = ref<ProductPublic[]>([]);
const products = computed(() =>
  source.value === 'recently_viewed' ? viewed.value : (props.section.products ?? []),
);

onMounted(async () => {
  if (source.value !== 'recently_viewed') return;
  const ids = readRecentlyViewed().slice(0, limit.value);
  try {
    viewed.value = await getProductsByIds(ids);
  } catch {
    viewed.value = [];
  }
});
</script>

<style scoped lang="scss">
// Same heading as the other homepage sections (their rules are scoped to
// the page, which reach this component's root only).
.home-section__head {
  margin-bottom: 24px;
  display: flex;
  align-items: baseline;
  gap: 14px;
}

.home-section__title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.015em;
}

.current-order {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-surface);
  color: var(--n-ink);
  text-decoration: none;

  &:hover {
    border-color: var(--n-line-2);
  }
}

.current-order__icon {
  flex: none;
  color: var(--n-ink-2);
}

.current-order__body {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.current-order__number {
  font-weight: 600;
}

.current-order__meta {
  color: var(--n-ink-2);
  font-size: 14px;
}

.current-order__link {
  flex: none;
  font-size: 14px;
  font-weight: 500;
}

@media (max-width: 599px) {
  .current-order__link {
    display: none;
  }
}
</style>
