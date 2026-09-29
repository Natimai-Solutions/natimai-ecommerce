<template>
  <!-- fff : le footer défile avec le contenu (non fixé) -->
  <q-layout view="hHh lpR fff">
    <q-header class="app-header">
      <div class="app-header__bar page-container">
        <q-btn
          flat
          round
          icon="ph:list"
          aria-label="Menu"
          class="lt-md app-header__icon"
          @click="toggleDrawer"
        />

        <router-link to="/" class="app-header__logo">Natimai</router-link>

        <nav class="gt-sm app-header__nav" aria-label="Navigation principale">
          <router-link
            :to="{ name: 'catalogue' }"
            class="app-header__link"
            :aria-current="$route.name === 'catalogue' ? 'page' : undefined"
          >
            Catalogue
          </router-link>
        </nav>

        <form class="gt-sm app-header__search" role="search" @submit.prevent="submitSearch">
          <label for="header-search" class="sr-only">Rechercher dans le catalogue</label>
          <div class="search-field">
            <q-icon name="ph:magnifying-glass" size="18px" class="search-field__icon" />
            <input
              id="header-search"
              ref="searchInput"
              v-model="searchText"
              type="search"
              placeholder="Produit, référence ou EAN"
              autocomplete="off"
              class="search-field__input"
            />
            <kbd class="search-field__kbd font-mono" aria-hidden="true">/</kbd>
          </div>
        </form>

        <div class="app-header__actions">
          <!-- Devise d'affichage (présentationnelle ; paiement en XPF) -->
          <label v-if="currencyStore.available.length > 1" class="gt-sm">
            <span class="sr-only">Devise d'affichage</span>
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
            :aria-label="$q.dark.isActive ? 'Passer en mode clair' : 'Passer en mode sombre'"
            @click="toggleTheme"
          />

          <template v-if="authStore.isAuthenticated">
            <q-btn
              flat
              no-caps
              class="gt-sm app-header__text-btn"
              label="Mon compte"
              :to="{ name: 'account' }"
            />
            <q-btn
              flat
              round
              class="gt-sm app-header__icon"
              icon="ph:sign-out"
              aria-label="Déconnexion"
              @click="onLogout"
            />
          </template>
          <q-btn
            v-else
            flat
            no-caps
            class="gt-sm app-header__text-btn"
            label="Connexion"
            :to="{ name: 'login' }"
          />

          <q-btn
            flat
            round
            class="app-header__icon"
            :to="{ name: 'cart' }"
            :aria-label="cartCount > 0 ? `Panier, ${cartCount} articles` : 'Panier'"
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
        <label for="header-search-mobile" class="sr-only">Rechercher dans le catalogue</label>
        <div class="search-field">
          <q-icon name="ph:magnifying-glass" size="18px" class="search-field__icon" />
          <input
            id="header-search-mobile"
            v-model="searchText"
            type="search"
            placeholder="Produit, référence ou EAN"
            autocomplete="off"
            class="search-field__input"
          />
        </div>
      </form>
    </q-header>

    <!-- Menu mobile -->
    <q-drawer v-model="drawerOpen" overlay behavior="mobile" :width="300" class="app-menu">
      <nav class="app-menu__inner" aria-label="Menu">
        <router-link :to="{ name: 'catalogue' }" class="app-menu__link" @click="drawerOpen = false">
          Catalogue
        </router-link>
        <router-link :to="{ name: 'cart' }" class="app-menu__link" @click="drawerOpen = false">
          Panier
          <span v-if="cartCount > 0" class="font-mono text-subtle">{{ cartCount }}</span>
        </router-link>
        <router-link
          v-if="authStore.isAuthenticated"
          :to="{ name: 'account' }"
          class="app-menu__link"
          @click="drawerOpen = false"
        >
          Mon compte
        </router-link>
        <button
          v-if="authStore.isAuthenticated"
          type="button"
          class="app-menu__link"
          @click="onLogout"
        >
          Déconnexion
        </button>
        <router-link
          v-else
          :to="{ name: 'login' }"
          class="app-menu__link"
          @click="drawerOpen = false"
        >
          Connexion
        </router-link>

        <label v-if="currencyStore.available.length > 1" class="app-menu__currency">
          <span>Devise d'affichage</span>
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

    <q-page-container>
      <router-view />
    </q-page-container>

    <q-footer class="app-footer">
      <div class="app-footer__inner page-container">
        <span>© {{ currentYear }} Natimai Solutions. Tous droits réservés.</span>
        <nav class="app-footer__links" aria-label="Informations légales">
          <router-link :to="{ name: 'cgv' }">CGV</router-link>
          <router-link :to="{ name: 'mentions-legales' }">Mentions légales</router-link>
          <router-link :to="{ name: 'confidentialite' }">Confidentialité &amp; cookies</router-link>
        </nav>
      </div>
    </q-footer>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import CartDrawer from 'src/components/CartDrawer.vue';
import { useCartStore } from 'src/stores/cart';
import { useAuthStore } from 'src/stores/auth';
import { useCurrencyStore } from 'src/stores/currency';
import { toggleTheme } from 'src/utils/theme';

const drawerOpen = ref(false);
const cartStore = useCartStore();
const authStore = useAuthStore();
const currencyStore = useCurrencyStore();
const route = useRoute();
const router = useRouter();
const cartCount = computed(() => cartStore.totalItems);
const currentYear = new Date().getFullYear();

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
