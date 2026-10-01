<template>
  <q-layout view="lHh LpR lFf" class="admin-layout">
    <q-header class="admin-topbar">
      <q-toolbar class="admin-topbar__bar">
        <q-btn
          flat
          round
          dense
          icon="ph:list"
          :aria-label="$t('layout.open_menu')"
          class="lt-md"
          @click="drawer = !drawer"
        />
        <q-space />
        <q-btn
          flat
          round
          dense
          :icon="themeIcon"
          :aria-label="$t('layout.theme', { label: themeLabel })"
          data-testid="admin-theme"
        >
          <q-tooltip>{{ $t('layout.theme', { label: themeLabel }) }}</q-tooltip>
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
                <q-item-section>{{ $t(option.label) }}</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
        <q-btn flat no-caps dense class="admin-topbar__account" data-testid="admin-account">
          <span class="admin-topbar__avatar" aria-hidden="true">{{ initials }}</span>
          <span class="admin-topbar__email gt-xs">{{ me?.email ?? $t('layout.account') }}</span>
          <q-icon name="ph:caret-down" size="14px" />
          <q-menu anchor="bottom right" self="top right">
            <q-list dense class="admin-menu">
              <q-item v-if="me" class="admin-menu__who">
                <q-item-section>
                  <q-item-label>{{ me.full_name || me.email }}</q-item-label>
                  <q-item-label caption>{{ $t('layout.administrator') }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-separator v-if="me" />
              <q-item v-close-popup clickable to="/security" data-testid="admin-security">
                <q-item-section avatar
                  ><q-icon name="ph:shield-check" size="18px"
                /></q-item-section>
                <q-item-section>{{ $t('layout.security') }}</q-item-section>
              </q-item>
              <q-item>
                <q-item-section avatar><q-icon name="ph:translate" size="18px" /></q-item-section>
                <q-item-section>
                  <q-btn-toggle
                    :model-value="currentLocale"
                    :options="
                      localeOptions.map((o) => ({ value: o.value, label: o.value.toUpperCase() }))
                    "
                    dense
                    no-caps
                    unelevated
                    toggle-color="primary"
                    :aria-label="$t('layout.language')"
                    data-testid="admin-locale"
                    @update:model-value="setLocale"
                  />
                </q-item-section>
              </q-item>
              <q-item v-close-popup clickable data-testid="admin-logout" @click="onLogout">
                <q-item-section avatar><q-icon name="ph:sign-out" size="18px" /></q-item-section>
                <q-item-section>{{ $t('layout.logout') }}</q-item-section>
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
            <span>{{ $t('layout.administration') }}</span>
          </span>
        </router-link>

        <nav class="admin-nav__scroll" :aria-label="$t('layout.admin_nav')">
          <router-link
            to="/"
            class="admin-nav__link"
            exact-active-class="admin-nav__link--active"
            data-testid="nav-dashboard"
          >
            <q-icon name="ph:squares-four" size="18px" />
            <span>{{ $t('layout.dashboard') }}</span>
          </router-link>
          <section v-for="section in nav" :key="section.label" class="admin-nav__section">
            <h2 class="admin-nav__label">{{ $t(section.label) }}</h2>
            <router-link
              v-for="link in section.links"
              :key="link.to"
              :to="link.to"
              class="admin-nav__link"
              active-class="admin-nav__link--active"
              :data-testid="`nav-${link.to.slice(1)}`"
            >
              <q-icon :name="link.icon" size="18px" />
              <span>{{ $t(link.label) }}</span>
            </router-link>
          </section>
        </nav>

        <router-link
          v-if="shopConfig.isSimple"
          to="/modules"
          class="admin-nav__mode"
          :title="$t('layout.simple_title')"
        >
          <q-icon name="ph:leaf" size="16px" />
          {{ $t('layout.simple_mode') }}
        </router-link>
      </div>
    </q-drawer>

    <q-page-container>
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useAdminLocale } from '@/composables/useAdminLocale';
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import { useRouter } from 'vue-router';

import { getMe, type Me } from '@/api/me';
import { useAuthStore } from '@/stores/auth';
import { useShopConfigStore } from '@/stores/shopConfig';
import { moduleOfPath } from '@/utils/modules';
import { readThemePreference, setThemePreference, type ThemePreference } from '@/utils/theme';

const { t } = useI18n();
const { current: currentLocale, options: localeOptions, setLocale } = useAdminLocale();

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

const allNav: NavSection[] = [
  {
    label: 'layout.nav.sales',
    links: [
      { label: 'layout.nav.orders', icon: 'ph:receipt', to: '/orders' },
      {
        label: 'layout.nav.payment_validations',
        icon: 'ph:check-square-offset',
        to: '/payment-validations',
      },
      { label: 'layout.nav.quote_requests', icon: 'ph:note-pencil', to: '/quote-requests' },
      { label: 'layout.nav.invoices', icon: 'ph:file-text', to: '/invoices' },
      { label: 'layout.nav.credit_notes', icon: 'ph:receipt-x', to: '/credit-notes' },
      { label: 'layout.nav.abandoned_carts', icon: 'ph:shopping-bag', to: '/abandoned-carts' },
    ],
  },
  {
    label: 'layout.nav.catalogue',
    links: [
      { label: 'layout.nav.products', icon: 'ph:package', to: '/products' },
      { label: 'layout.nav.categories', icon: 'ph:folders', to: '/categories' },
      { label: 'layout.nav.specs', icon: 'ph:sliders-horizontal', to: '/spec-definitions' },
      { label: 'layout.nav.promotions', icon: 'ph:seal-percent', to: '/promotions' },
      { label: 'layout.nav.discounts', icon: 'ph:tag', to: '/discounts' },
    ],
  },
  {
    label: 'layout.nav.logistics',
    links: [
      { label: 'layout.nav.departures', icon: 'ph:calendar-check', to: '/grouped-departures' },
      { label: 'layout.nav.shipping', icon: 'ph:truck', to: '/shipping' },
      { label: 'layout.nav.inventory', icon: 'ph:warehouse', to: '/inventory' },
      { label: 'layout.nav.routes', icon: 'ph:path', to: '/logistics-routes' },
      { label: 'layout.nav.carriers', icon: 'ph:mailbox', to: '/carriers' },
      { label: 'layout.nav.suppliers', icon: 'ph:storefront', to: '/suppliers' },
      { label: 'layout.nav.supplier_orders', icon: 'ph:clipboard-text', to: '/supplier-orders' },
    ],
  },
  {
    label: 'layout.nav.customers',
    links: [
      { label: 'layout.nav.users', icon: 'ph:users', to: '/users' },
      { label: 'layout.nav.group_requests', icon: 'ph:user-plus', to: '/group-upgrade-requests' },
      { label: 'layout.nav.addresses', icon: 'ph:map-pin', to: '/addresses' },
    ],
  },
  {
    label: 'layout.nav.pricing',
    links: [
      { label: 'layout.nav.price_groups', icon: 'ph:users-three', to: '/price-groups' },
      { label: 'layout.nav.tax_rates', icon: 'ph:percent', to: '/tax-rates' },
      { label: 'layout.nav.customs', icon: 'ph:gavel', to: '/customs-rates' },
      { label: 'layout.nav.currency_rates', icon: 'ph:arrows-left-right', to: '/currency-rates' },
      { label: 'layout.nav.payment_methods', icon: 'ph:credit-card', to: '/payment-eligibility' },
    ],
  },
  {
    label: 'layout.nav.system',
    links: [
      { label: 'layout.nav.homepage', icon: 'ph:house', to: '/homepage' },
      { label: 'layout.nav.pages', icon: 'ph:article', to: '/pages' },
      { label: 'layout.nav.modules', icon: 'ph:toggle-right', to: '/modules' },
      { label: 'layout.nav.audit', icon: 'ph:clipboard-text', to: '/audit-log' },
      { label: 'layout.nav.settings', icon: 'ph:gear', to: '/system-settings' },
    ],
  },
];

/** Screens of a switched-off module leave the menu (Admin → Modules). */
const nav = computed<NavSection[]>(() =>
  allNav
    .map((section) => ({
      ...section,
      links: section.links.filter((link) => {
        const module = moduleOfPath(link.to);
        return !module || shopConfig.moduleOn(module);
      }),
    }))
    .filter((section) => section.links.length > 0),
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
  { value: 'auto', label: 'layout.theme_auto', icon: 'ph:circle-half' },
  { value: 'light', label: 'layout.theme_light', icon: 'ph:sun' },
  { value: 'dark', label: 'layout.theme_dark', icon: 'ph:moon' },
];
const theme = ref<ThemePreference>(readThemePreference());
const themeLabel = computed(() =>
  t(THEME_OPTIONS.find((option) => option.value === theme.value)?.label ?? 'layout.theme_auto'),
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
