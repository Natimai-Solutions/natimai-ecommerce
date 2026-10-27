<template>
  <section
    class="ship-estimate"
    :aria-label="$t('ship_estimate.title')"
    data-testid="ship-estimate"
  >
    <h3 class="ship-estimate__title">{{ $t('ship_estimate.title') }}</h3>
    <q-select
      v-model="placeId"
      :options="islandOptions"
      :label="$t('ship_estimate.island')"
      :loading="loadingZones"
      dense
      outlined
      emit-value
      map-options
      options-dense
      clearable
      data-testid="ship-estimate-island"
      @update:model-value="onIsland"
    />

    <div v-if="loading" class="ship-estimate__rows" aria-busy="true">
      <q-skeleton v-for="n in 2" :key="n" type="text" />
    </div>
    <p v-else-if="error" class="ship-estimate__hint">{{ error }}</p>
    <template v-else-if="placeId && estimate">
      <ul v-if="estimate.options.length > 0" class="ship-estimate__rows">
        <li
          v-for="option in estimate.options"
          :key="option.delivery_type"
          class="ship-estimate__row"
        >
          <span>
            {{ option.label || option.delivery_type }}
            <span v-if="option.eta_days" class="text-subtle">
              · {{ $t('ship_estimate.eta', { n: option.eta_days }, option.eta_days) }}
            </span>
          </span>
          <span class="font-mono">{{ money(option.amount) }}</span>
        </li>
      </ul>
      <p v-else class="ship-estimate__hint">{{ $t('ship_estimate.none') }}</p>
      <p v-if="customsFee > 0" class="ship-estimate__hint">
        {{ $t('ship_estimate.customs', { amount: money(estimate.customs_declaration_fee) }) }}
      </p>
    </template>
    <p v-else class="ship-estimate__hint">{{ $t('ship_estimate.pick') }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { getGuestLastLegOptions, getLastLegOptions, type LastLegOptionsResponse } from '@/api/cart';
import { getGeoTree, type PlaceTreeNode } from '@/api/addresses';
import { useAuthStore } from '@/stores/auth';
import { currentGuestToken, useCartStore } from '@/stores/cart';
import { useCurrencyStore } from '@/stores/currency';
import { useShopModulesStore } from '@/stores/shopModules';

/**
 * « Le prix final rendu, avant de commander » : the visitor picks their
 * island and sees each delivery mode priced for this cart, signed in or not.
 * The island is remembered in the browser for the next visit.
 */
const ISLAND_KEY = 'shipping_estimate_place';

const { t } = useI18n();
const auth = useAuthStore();
const cartStore = useCartStore();
const currencyStore = useCurrencyStore();
const shop = useShopModulesStore();

const zones = ref<PlaceTreeNode[]>([]);
const loadingZones = ref(false);
const placeId = ref<string | null>(null);
const estimate = ref<LastLegOptionsResponse | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

/** Leaves of the zone tree (the islands), named with their archipelago. */
const islandOptions = computed(() => {
  const out: { label: string; value: string }[] = [];
  const walk = (nodes: PlaceTreeNode[], parent: string | null) => {
    for (const node of nodes) {
      if (node.children.length === 0) {
        out.push({ label: parent ? `${node.name} (${parent})` : node.name, value: node.id });
      } else {
        walk(node.children, node.name);
      }
    }
  };
  walk(zones.value, null);
  return out.sort((a, b) => a.label.localeCompare(b.label));
});

const customsFee = computed(
  () => Number.parseFloat(estimate.value?.customs_declaration_fee ?? '0') || 0,
);

function money(raw: string): string {
  const value = Number.parseFloat(raw);
  return currencyStore.format(Number.isFinite(value) ? value : 0);
}

function remembered(): string | null {
  try {
    return localStorage.getItem(ISLAND_KEY);
  } catch {
    return null;
  }
}

function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(ISLAND_KEY, id);
    else localStorage.removeItem(ISLAND_KEY);
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
}

async function loadEstimate() {
  if (!placeId.value) {
    estimate.value = null;
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    if (auth.isAuthenticated) {
      estimate.value = await getLastLegOptions(null, placeId.value);
    } else {
      const token = currentGuestToken();
      estimate.value = token ? await getGuestLastLegOptions(token, placeId.value) : null;
    }
  } catch {
    error.value = t('ship_estimate.failed');
  } finally {
    loading.value = false;
  }
}

function onIsland(id: string | null) {
  remember(id);
  void loadEstimate();
}

async function loadZones() {
  loadingZones.value = true;
  try {
    await shop.load();
    zones.value = await getGeoTree(shop.config.country_code || 'PF');
  } catch {
    zones.value = [];
  } finally {
    loadingZones.value = false;
  }
  const saved = remembered();
  if (saved && islandOptions.value.some((option) => option.value === saved)) {
    placeId.value = saved;
    void loadEstimate();
  }
}

// The weight changes with the cart: price again.
watch(
  () => cartStore.items.map((item) => `${item.product_id}:${item.quantity}`).join(','),
  () => void loadEstimate(),
);

onMounted(() => void loadZones());
</script>

<style scoped lang="scss">
.ship-estimate {
  display: grid;
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid var(--n-line);
}

.ship-estimate__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
}

.ship-estimate__rows {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.ship-estimate__row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.9rem;
}

.ship-estimate__hint {
  margin: 0;
  font-size: 0.85rem;
  color: var(--n-ink-3);
}
</style>
