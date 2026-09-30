<template>
  <q-layout view="lHh LpR lFf" class="admin-layout">
    <q-header class="admin-topbar">
      <q-toolbar class="admin-topbar__bar">
        <q-btn
          flat
          round
          dense
          icon="ph:list"
          aria-label="Ouvrir le menu"
          class="lt-md"
          @click="drawer = !drawer"
        />
        <q-space />
        <q-btn
          flat
          round
          dense
          :icon="themeIcon"
          :aria-label="`Thème : ${themeLabel}`"
          data-testid="admin-theme"
        >
          <q-tooltip>Thème : {{ themeLabel }}</q-tooltip>
          <q-menu anchor="bottom right" self="top right">
            <q-list dense class="admin-menu">
              <q-item
                v-for="option in THEME_OPTIONS"
                :key="option.value"
                v-close-popup
                clickable
                :active="theme === option.value"
                active-class="admin-menu__active"
                :data-testid="`theme-${option.value}`"
                @click="chooseTheme(option.value)"
              >
                <q-item-section avatar><q-icon :name="option.icon" size="18px" /></q-item-section>
                <q-item-section>{{ option.label }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
        <q-btn flat no-caps dense class="admin-topbar__account" data-testid="admin-account">
          <span class="admin-topbar__avatar" aria-hidden="true">{{ initials }}</span>
          <span class="admin-topbar__email gt-xs">{{ me?.email ?? 'Compte' }}</span>
          <q-icon name="ph:caret-down" size="14px" />
          <q-menu anchor="bottom right" self="top right">
            <q-list dense class="admin-menu">
              <q-item v-if="me" class="admin-menu__who">
                <q-item-section>
                  <q-item-label>{{ me.full_name || me.email }}</q-item-label>
                  <q-item-label caption>Administrateur</q-item-label>
                </q-item-section>
              </q-item>
              <q-separator v-if="me" />
              <q-item v-close-popup clickable data-testid="admin-logout" @click="onLogout">
                <q-item-section avatar><q-icon name="ph:sign-out" size="18px" /></q-item-section>
                <q-item-section>Se déconnecter</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="drawer" show-if-above :width="248" :breakpoint="1023" class="admin-nav">
      <div class="admin-nav__inner">
        <router-link to="/" class="admin-nav__brand">
          <span class="admin-nav__mark" aria-hidden="true">N</span>
          <span class="admin-nav__brand-text">
            <strong>{{ shopName }}</strong>
            <span>Administration</span>
          </span>
        </router-link>

        <nav class="admin-nav__scroll" aria-label="Navigation de l'administration">
          <router-link
            to="/"
            class="admin-nav__link"
            exact-active-class="admin-nav__link--active"
            data-testid="nav-dashboard"
          >
            <q-icon name="ph:squares-four" size="18px" />
            <span>Tableau de bord</span>
          </router-link>
          <section v-for="section in nav" :key="section.label" class="admin-nav__section">
            <h2 class="admin-nav__label">{{ section.label }}</h2>
            <router-link
              v-for="link in section.links"
              :key="link.to"
              :to="link.to"
              class="admin-nav__link"
              active-class="admin-nav__link--active"
              :data-testid="`nav-${link.to.slice(1)}`"
            >
              <q-icon :name="link.icon" size="18px" />
              <span>{{ link.label }}</span>
            </router-link>
          </section>
        </nav>

        <router-link
          v-if="shopConfig.isSimple"
          to="/system-settings"
          class="admin-nav__mode"
          title="Certains écrans (fournisseurs, douane, trajets) sont masqués"
        >
          <q-icon name="ph:leaf" size="16px" />
          Mode simple
        </router-link>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import { useRouter } from 'vue-router';

import { getMe, type Me } from '@/api/me';
import { useAuthStore } from '@/stores/auth';
import { useShopConfigStore } from '@/stores/shopConfig';
import { readThemePreference, setThemePreference, type ThemePreference } from '@/utils/theme';

const $q = useQuasar();
const auth = useAuthStore();
const router = useRouter();
const shopConfig = useShopConfigStore();
const drawer = ref(false);

interface NavLink {
  label: string;
  icon: string;
  to: string;
}
interface NavSection {
  label: string;
  links: NavLink[];
}

/**
 * Écrans qui n'ont de sens qu'avec des fournisseurs, de la douane ou une
 * logistique multi-étapes. Masqués en mode simple ; les routes restent
 * accessibles par leur adresse.
 */
const FULL_MODE_ONLY = new Set([
  '/spec-definitions',
  '/customs-rates',
  '/currency-rates',
  '/logistics-routes',
  '/suppliers',
  '/supplier-orders',
]);

const allNav: NavSection[] = [
  {
    label: 'Ventes',
    links: [
      { label: 'Commandes', icon: 'ph:receipt', to: '/orders' },
      {
        label: 'Validation des paiements',
        icon: 'ph:check-square-offset',
        to: '/payment-validations',
      },
      { label: 'Demandes de devis', icon: 'ph:note-pencil', to: '/quote-requests' },
      { label: 'Factures', icon: 'ph:file-text', to: '/invoices' },
      { label: 'Avoirs', icon: 'ph:receipt-x', to: '/credit-notes' },
      { label: 'Paniers abandonnés', icon: 'ph:shopping-bag', to: '/abandoned-carts' },
    ],
  },
  {
    label: 'Catalogue',
    links: [
      { label: 'Produits', icon: 'ph:package', to: '/products' },
      { label: 'Catégories', icon: 'ph:folders', to: '/categories' },
      { label: 'Caractéristiques', icon: 'ph:sliders-horizontal', to: '/spec-definitions' },
      { label: 'Codes promo', icon: 'ph:tag', to: '/discounts' },
    ],
  },
  {
    label: 'Logistique',
    links: [
      { label: 'Départs groupés', icon: 'ph:calendar-check', to: '/grouped-departures' },
      { label: 'Expéditions', icon: 'ph:truck', to: '/shipping' },
      { label: 'Inventaire', icon: 'ph:warehouse', to: '/inventory' },
      { label: 'Trajets et lieux', icon: 'ph:path', to: '/logistics-routes' },
      { label: 'Transporteurs', icon: 'ph:mailbox', to: '/carriers' },
      { label: 'Fournisseurs', icon: 'ph:storefront', to: '/suppliers' },
      { label: 'Commandes fournisseurs', icon: 'ph:clipboard-text', to: '/supplier-orders' },
    ],
  },
  {
    label: 'Clients',
    links: [
      { label: 'Utilisateurs', icon: 'ph:users', to: '/users' },
      { label: 'Demandes de groupe', icon: 'ph:user-plus', to: '/group-upgrade-requests' },
      { label: 'Adresses', icon: 'ph:map-pin', to: '/addresses' },
    ],
  },
  {
    label: 'Tarifs et paiement',
    links: [
      { label: 'Groupes tarifaires', icon: 'ph:users-three', to: '/price-groups' },
      { label: 'Taux de TVA', icon: 'ph:percent', to: '/tax-rates' },
      { label: 'Douane par catégorie', icon: 'ph:gavel', to: '/customs-rates' },
      { label: 'Taux de change', icon: 'ph:arrows-left-right', to: '/currency-rates' },
      { label: 'Moyens de paiement', icon: 'ph:credit-card', to: '/payment-eligibility' },
    ],
  },
  {
    label: 'Site et système',
    links: [
      { label: 'Accueil du site', icon: 'ph:house', to: '/homepage' },
      { label: 'Pages du site', icon: 'ph:article', to: '/pages' },
      { label: 'Paramètres', icon: 'ph:gear', to: '/system-settings' },
    ],
  },
];

const nav = computed<NavSection[]>(() =>
  shopConfig.isSimple
    ? allNav
        .map((section) => ({
          ...section,
          links: section.links.filter((link) => !FULL_MODE_ONLY.has(link.to)),
        }))
        .filter((section) => section.links.length > 0)
    : allNav,
);

const shopName = computed(() => shopConfig.config?.shop_name || 'Natimai');

// --- Compte ---
const me = ref<Me | null>(null);
const initials = computed(() => {
  const source = me.value?.full_name || me.value?.email || '';
  const parts = source.split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '·';
});

onMounted(() => {
  void shopConfig.load();
  getMe()
    .then((data) => (me.value = data))
    .catch(() => (me.value = null));
});

function onLogout() {
  void auth.logout();
  void router.replace('/login');
}

// --- Thème ---
const THEME_OPTIONS: { value: ThemePreference; label: string; icon: string }[] = [
  { value: 'auto', label: 'Comme le système', icon: 'ph:circle-half' },
  { value: 'light', label: 'Clair', icon: 'ph:sun' },
  { value: 'dark', label: 'Sombre', icon: 'ph:moon' },
];
const theme = ref<ThemePreference>(readThemePreference());
const themeLabel = computed(
  () => THEME_OPTIONS.find((option) => option.value === theme.value)?.label ?? '',
);
const themeIcon = computed(() => {
  if (theme.value === 'auto') return 'ph:circle-half';
  return $q.dark.isActive ? 'ph:moon' : 'ph:sun';
});

function chooseTheme(value: ThemePreference) {
  theme.value = value;
  setThemePreference(value);
}
</script>

<style scoped lang="scss">
.admin-layout {
  background: var(--n-bg);
}

.admin-topbar {
  background: color-mix(in srgb, var(--n-bg) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(10px);
  color: var(--n-ink);
  border-bottom: 1px solid var(--n-line);
}

.admin-topbar__bar {
  min-height: 56px;
  padding: 0 16px 0 20px;
  gap: 6px;
}

.admin-topbar__account {
  padding: 4px 8px 4px 4px;
  border-radius: 999px;

  :deep(.q-btn__content) {
    gap: 8px;
  }
}

.admin-topbar__avatar {
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  background: var(--n-ink);
  color: var(--n-on-ink);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.admin-topbar__email {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--n-ink-2);
}

.admin-menu {
  min-width: 200px;
  padding: 6px;

  .q-item {
    border-radius: 6px;
    min-height: 36px;
  }

  .q-item__section--avatar {
    min-width: 32px;
  }
}

.admin-menu__active {
  background: var(--n-tile);
  color: var(--n-ink);
}

.admin-menu__who {
  pointer-events: none;
}

.admin-nav {
  :deep(.q-drawer) {
    background: var(--n-surface);
    border-right: 1px solid var(--n-line);
  }
}

.admin-nav__inner {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.admin-nav__brand {
  margin: 0 12px;
  padding: 16px 8px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--n-ink);
  text-decoration: none;
  border-bottom: 1px solid var(--n-line);
}

.admin-nav__mark {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--n-ink);
  color: var(--n-on-ink);
  font-weight: 700;
  font-size: 15px;
  letter-spacing: -0.02em;
}

.admin-nav__brand-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.2;

  strong {
    font-size: 14px;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  span {
    font-size: 12px;
    color: var(--n-ink-3);
  }
}

.admin-nav__scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 12px 16px;
}

.admin-nav__section {
  margin-top: 18px;
}

.admin-nav__label {
  margin: 0 0 4px;
  padding: 0 10px;
  font-size: 11px;
  line-height: 1.6;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--n-ink-3);
}

.admin-nav__link {
  position: relative;
  min-height: 34px;
  padding: 6px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 6px;
  color: var(--n-ink-2);
  font-size: 13.5px;
  line-height: 1.3;
  text-decoration: none;
  transition: background-color 0.15s ease;

  .q-icon {
    color: var(--n-ink-3);
  }

  &:hover {
    background: var(--n-tile);
    color: var(--n-ink);
  }

  &--active {
    background: var(--n-tile);
    color: var(--n-ink);
    font-weight: 500;

    .q-icon {
      color: var(--n-accent);
    }

    &::before {
      content: '';
      position: absolute;
      left: -12px;
      top: 8px;
      bottom: 8px;
      width: 2px;
      border-radius: 2px;
      background: var(--n-accent);
    }
  }
}

.admin-nav__mode {
  margin: 0 12px 12px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  font-size: 12px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-ink);
    border-color: var(--n-line-2);
  }
}
</style>
