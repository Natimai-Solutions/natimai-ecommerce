<template>
  <!-- fff : le footer défile avec le contenu (non fixé) -->
  <q-layout view="hHh lpR fff">
    <q-header class="app-header">
      <div class="app-header__bar page-container">
        <q-btn
          flat
          round
          icon="ph:list"
          aria-label="$t('layout.menu')"
          class="lt-md app-header__icon"
          @click="toggleDrawer"
        />

        <router-link to="/" class="app-header__logo" :aria-label="ownerName">
          <img
            v-if="logo"
            :src="logo.src"
            :srcset="logo.srcset ?? undefined"
            :width="logo.width"
            :height="logo.height"
            :alt="ownerName"
            class="app-header__logo-img"
          />
          <template v-else>{{ ownerName }}</template>
        </router-link>

        <nav class="gt-sm app-header__nav" :aria-label="$t('layout.main_nav')">
          <router-link
            :to="{ name: 'catalogue' }"
            class="app-header__link"
            :aria-current="$route.name === 'catalogue' ? 'page' : undefined"
          >
            {{ $t('layout.catalogue') }}
          </router-link>
        </nav>

        <form class="gt-sm app-header__search" role="search" @submit.prevent="submitSearch">
          <label for="header-search" class="sr-only">{{ $t('layout.search_label') }}</label>
          <div class="search-field">
            <q-icon name="ph:magnifying-glass" size="18px" class="search-field__icon" />
            <input
              id="header-search"
              ref="searchInput"
              v-model="searchText"
              type="search"
              :placeholder="$t('layout.search_placeholder')"
              autocomplete="off"
              class="search-field__input"
            />
            <!-- Rappel du raccourci clavier « / » : infobulle au survol,
                 masqué sur les écrans tactiles ou étroits où il n'a pas de sens. -->
            <kbd
              class="search-field__kbd font-mono"
              :title="$t('layout.search_shortcut')"
              aria-hidden="true"
              >/<q-tooltip anchor="bottom middle" self="top middle" :offset="[0, 8]">
                {{ $t('layout.search_shortcut') }}
              </q-tooltip></kbd
            >
          </div>
        </form>

        <div class="app-header__actions">
          <!-- Langue de l'interface (R7) -->
          <label v-if="localeOptions.length > 1" class="gt-sm">
            <span class="sr-only">{{ $t('common.language') }}</span>
            <select
              class="app-header__currency"
              :value="currentLocale"
              data-testid="locale-select"
              @change="onLocaleChange"
            >
              <option v-for="opt in localeOptions" :key="opt.value" :value="opt.value">
                {{ opt.value.toUpperCase() }}
              </option>
            </select>
          </label>

          <!-- Devise d'affichage (présentationnelle ; paiement dans la devise de référence) -->
          <label v-if="currencyStore.available.length > 1" class="gt-sm">
            <span class="sr-only">{{ $t('common.currency') }}</span>
            <select
              class="app-header__currency font-mono"
              :value="currencyStore.currency"
              @change="onCurrencyChange"
            >
              <option v-for="code in currencyStore.available" :key="code" :value="code">
                {{ code }}
              </option>
            </select>
          </label>

          <q-btn
            flat
            round
            class="app-header__icon"
            :icon="$q.dark.isActive ? 'ph:sun' : 'ph:moon'"
            :aria-label="$q.dark.isActive ? $t('layout.theme_light') : $t('layout.theme_dark')"
            @click="toggleTheme"
          />

          <template v-if="authStore.isAuthenticated">
            <q-btn
              flat
              no-caps
              class="gt-sm app-header__text-btn"
              icon="ph:user-circle"
              :label="authStore.displayName ?? $t('layout.account')"
              :aria-label="$t('layout.account')"
              :to="{ name: 'account' }"
              data-testid="header-account"
            />
            <q-btn
              flat
              round
              class="gt-sm app-header__icon"
              icon="ph:sign-out"
              :aria-label="$t('layout.logout')"
              @click="onLogout"
            />
          </template>
          <q-btn
            v-else
            flat
            no-caps
            class="gt-sm app-header__text-btn"
            :label="$t('layout.login')"
            :to="{ name: 'login' }"
          />

          <q-btn
            flat
            round
            class="app-header__icon"
            :to="{ name: 'cart' }"
            :aria-label="
              cartCount > 0 ? $t('layout.cart_with_count', { count: cartCount }) : $t('layout.cart')
            "
          >
            <q-icon name="ph:shopping-bag" size="22px" />
            <span v-if="cartCount > 0" class="app-header__badge font-mono" aria-hidden="true">
              {{ cartCount }}
            </span>
          </q-btn>
        </div>
      </div>

      <!-- Recherche mobile : toujours visible sous la barre -->
      <form class="lt-md app-header__search-mobile" role="search" @submit.prevent="submitSearch">
        <label for="header-search-mobile" class="sr-only">{{ $t('layout.search_label') }}</label>
        <div class="search-field">
          <q-icon name="ph:magnifying-glass" size="18px" class="search-field__icon" />
          <input
            id="header-search-mobile"
            v-model="searchText"
            type="search"
            :placeholder="$t('layout.search_placeholder')"
            autocomplete="off"
            class="search-field__input"
          />
        </div>
      </form>
    </q-header>

    <!-- Menu mobile -->
    <q-drawer v-model="drawerOpen" overlay behavior="mobile" :width="300" class="app-menu">
      <nav class="app-menu__inner" :aria-label="$t('layout.menu')">
        <router-link :to="{ name: 'catalogue' }" class="app-menu__link" @click="drawerOpen = false">
          {{ $t('layout.catalogue') }}
        </router-link>
        <router-link :to="{ name: 'cart' }" class="app-menu__link" @click="drawerOpen = false">
          {{ $t('layout.cart') }}
          <span v-if="cartCount > 0" class="font-mono text-subtle">{{ cartCount }}</span>
        </router-link>
        <router-link
          v-if="authStore.isAuthenticated"
          :to="{ name: 'account' }"
          class="app-menu__link"
          @click="drawerOpen = false"
        >
          {{ $t('layout.account') }}
        </router-link>
        <button
          v-if="authStore.isAuthenticated"
          type="button"
          class="app-menu__link"
          @click="onLogout"
        >
          {{ $t('layout.logout') }}
        </button>
        <router-link
          v-else
          :to="{ name: 'login' }"
          class="app-menu__link"
          @click="drawerOpen = false"
        >
          {{ $t('layout.login') }}
        </router-link>

        <label v-if="localeOptions.length > 1" class="app-menu__currency">
          <span>{{ $t('common.language') }}</span>
          <select class="app-header__currency" :value="currentLocale" @change="onLocaleChange">
            <option v-for="opt in localeOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
        </label>
        <label v-if="currencyStore.available.length > 1" class="app-menu__currency">
          <span>{{ $t('common.currency') }}</span>
          <select
            class="app-header__currency font-mono"
            :value="currencyStore.currency"
            @change="onCurrencyChange"
          >
            <option v-for="code in currencyStore.available" :key="code" :value="code">
              {{ code }}
            </option>
          </select>
        </label>
      </nav>
    </q-drawer>

    <CartDrawer />
    <CompareBar />

    <q-page-container>
      <NextDepartureBanner />
      <router-view />
    </q-page-container>

    <q-footer class="app-footer">
      <div class="app-footer__inner page-container">
        <span>{{ $t('layout.rights', { year: currentYear, name: ownerName }) }}</span>
        <nav class="app-footer__links" :aria-label="$t('layout.legal_nav')">
          <router-link :to="{ name: 'how-it-works' }">{{ $t('layout.how_it_works') }}</router-link>
          <router-link :to="{ name: 'cgv' }">{{ $t('layout.cgv') }}</router-link>
          <router-link :to="{ name: 'mentions-legales' }">{{
            $t('layout.legal_notice')
          }}</router-link>
          <router-link :to="{ name: 'confidentialite' }">{{ $t('layout.privacy') }}</router-link>
        </nav>
      </div>
    </q-footer>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, onServerPrefetch, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import CartDrawer from '@/components/CartDrawer.vue';
import CompareBar from '@/components/CompareBar.vue';
import { useCartStore } from '@/stores/cart';
import { useAuthStore } from '@/stores/auth';
import { useCurrencyStore } from '@/stores/currency';
import { toggleTheme } from '@/utils/theme';
import { useDepartureStore } from '@/stores/departure';
import NextDepartureBanner from '@/components/NextDepartureBanner.vue';
import { useLocale } from '@/composables/useLocale';
import { useShopModulesStore } from '@/stores/shopModules';

const drawerOpen = ref(false);
const cartStore = useCartStore();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();
const route = useRoute();
const departureStore = useDepartureStore();
const router = useRouter();
const cartCount = computed(() => cartStore.totalItems);
const currentYear = new Date().getFullYear();
const shop = useShopModulesStore();
const ownerName = computed(() => shop.config.shop_name || 'Natimai');
// The logo chosen in the back-office (R9 / T9); the shop name in text otherwise.
const logo = computed(() => shop.config.branding?.logo ?? null);
// The shop configuration is read during the server render too: the header
// (logo, name) and the icon links are right on the first paint.
onServerPrefetch(() => shop.load());
const { current: currentLocale, options: localeOptions, setLocale } = useLocale();

function onLocaleChange(event: Event) {
  void setLocale((event.target as HTMLSelectElement).value);
}

const searchInput = ref<HTMLInputElement | null>(null);
const searchText = ref('');

// Le champ reflète la recherche en cours du catalogue.
watch(
  () => route.query['q'],
  (q) => {
    searchText.value = typeof q === 'string' ? q : '';
  },
  { immediate: true },
);

function submitSearch() {
  const q = searchText.value.trim();
  void router.push({ name: 'catalogue', query: q ? { q } : {} });
  (document.activeElement as HTMLElement | null)?.blur();
}

// « / » place le curseur dans la recherche, sauf pendant une saisie.
function onKeydown(event: KeyboardEvent) {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
  if (!searchInput.value || searchInput.value.offsetParent === null) return;
  event.preventDefault();
  searchInput.value.focus();
}

function toggleDrawer() {
  drawerOpen.value = !drawerOpen.value;
}

function onCurrencyChange(event: Event) {
  void currencyStore.setCurrency((event.target as HTMLSelectElement).value);
}

function onLogout() {
  drawerOpen.value = false;
  void authStore.logout();
  void router.push({ name: 'catalogue' });
}

onMounted(() => {
  void cartStore.loadCart();
  void currencyStore.loadRates();
  void departureStore.load();
  void shop.load();
  window.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>

<style scoped lang="scss">
.app-header {
  background: var(--n-surface);
  color: var(--n-ink);
  border-bottom: 1px solid var(--n-line);
}

.app-header__bar {
  height: 64px;
  display: flex;
  align-items: center;
  gap: 32px;

  @media (max-width: 1023px) {
    height: 56px;
    gap: 4px;
    padding-left: 6px;
    padding-right: 6px;
  }
}

.app-header__logo {
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--n-ink);
  text-decoration: none;

  @media (max-width: 1023px) {
    flex-grow: 1;
    font-size: 18px;
  }
}

.app-header__logo-img {
  display: block;
  height: 40px;
  width: auto;
  max-width: 200px;
  object-fit: contain;
}

.app-header__nav {
  display: flex;
  gap: 24px;
}

.app-header__link {
  font-size: 14px;
  font-weight: 500;
  color: var(--n-ink-2);
  text-decoration: none;
  transition: color 0.2s ease;

  &:hover,
  &[aria-current='page'] {
    color: var(--n-ink);
  }
}

.app-header__search {
  flex-grow: 1;
  max-width: 560px;
  margin: 0 auto;
}

.app-header__search-mobile {
  padding: 0 16px 12px;
}

.search-field {
  height: 40px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-bg);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;

  &:focus-within {
    border-color: var(--n-accent);
    box-shadow: 0 0 0 3px var(--n-accent-soft);
  }

  .app-header__search-mobile & {
    height: 44px;
  }
}

.search-field__icon {
  color: var(--n-ink-3);
}

.search-field__input {
  flex-grow: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--n-ink);
  font: inherit;
  font-size: 14px;

  &::placeholder {
    color: var(--n-ink-3);
  }

  // Évite le zoom automatique d'iOS sur les champs < 16px.
  .app-header__search-mobile & {
    font-size: 16px;
  }
}

.search-field__kbd {
  padding: 1px 6px;
  border: 1px solid var(--n-line);
  border-radius: 4px;
  font-size: 11px;
  color: var(--n-ink-3);
  cursor: help;

  // Pas de clavier physique (tactile) ou pas la place : le rappel disparaît.
  @media (hover: none), (max-width: 1023px) {
    display: none;
  }
}

.app-header__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.app-header__icon {
  width: 40px;
  height: 40px;
  color: var(--n-ink);

  @media (max-width: 1023px) {
    width: 44px;
    height: 44px;
  }
}

.app-header__text-btn {
  min-height: 40px;
  padding: 0 12px;
  font-size: 14px;
  color: var(--n-ink);
}

.app-header__currency {
  height: 40px;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--n-ink-2);
  font-size: 13px;
  cursor: pointer;

  &:hover {
    background: var(--n-tile);
  }

  option {
    background: var(--n-surface);
    color: var(--n-ink);
  }
}

.app-header__badge {
  position: absolute;
  top: 3px;
  right: 1px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--n-accent);
  color: var(--n-on-accent);
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
}

.app-menu__inner {
  height: 100%;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--n-surface);
}

.app-menu__link {
  min-height: 48px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--n-ink);
  font: inherit;
  font-size: 16px;
  font-weight: 500;
  text-align: left;
  text-decoration: none;
  cursor: pointer;

  &:hover,
  &.router-link-active {
    background: var(--n-tile);
  }
}

.app-menu__currency {
  margin-top: auto;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--n-line);
  font-size: 14px;
  color: var(--n-ink-2);
}

.app-footer {
  position: static;
  background: transparent;
  color: var(--n-ink-3);
  border-top: 1px solid var(--n-line);
}

.app-footer__inner {
  padding-top: 28px;
  padding-bottom: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  font-size: 13px;

  @media (max-width: 767px) {
    flex-direction: column-reverse;
    align-items: flex-start;
    gap: 14px;
    padding-bottom: 32px;
  }
}

.app-footer__links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;

  a {
    color: inherit;
    text-decoration: none;
    transition: color 0.2s ease;

    &:hover {
      color: var(--n-accent);
    }
  }
}
</style>
