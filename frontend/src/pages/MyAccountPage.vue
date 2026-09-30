<template>
  <q-page class="account page-container app-page">
    <header class="account__head">
      <div>
        <h1 class="page-title">Mon compte</h1>
        <p class="account__greeting">
          <template v-if="profile?.full_name">Bonjour {{ firstName }}.</template>
          <span v-if="profile" class="account__email">{{ profile.email }}</span>
        </p>
      </div>
      <q-btn
        flat
        no-caps
        icon="ph:sign-out"
        label="Se déconnecter"
        class="account__logout"
        @click="onLogout"
      />
    </header>

    <div v-if="ready" class="account__layout">
      <nav class="account-nav" aria-label="Sections du compte">
        <router-link
          v-for="section in SECTIONS"
          :key="section.key"
          :to="{ name: 'account', query: section.key === 'overview' ? {} : { tab: section.key } }"
          class="account-nav__link"
          :aria-current="current.key === section.key ? 'page' : undefined"
          :data-testid="`account-nav-${section.key}`"
        >
          <q-icon :name="section.icon" size="20px" class="account-nav__icon" />
          <span>{{ section.label }}</span>
        </router-link>
      </nav>

      <div class="account__content">
        <keep-alive>
          <component :is="current.component" :key="current.key" @updated="onProfileUpdated" />
        </keep-alive>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue';
import { useMeta } from 'quasar';
import { useRoute, useRouter } from 'vue-router';

import AccountAddresses from '@/components/account/AccountAddresses.vue';
import AccountGroup from '@/components/account/AccountGroup.vue';
import AccountOrders from '@/components/account/AccountOrders.vue';
import AccountOverview from '@/components/account/AccountOverview.vue';
import AccountPreferences from '@/components/account/AccountPreferences.vue';
import AccountProfile from '@/components/account/AccountProfile.vue';
import AccountQuotes from '@/components/account/AccountQuotes.vue';
import AccountWishlist from '@/components/account/AccountWishlist.vue';
import { getMyProfile, type MyProfile } from '@/api/profile';
import { useAuthStore } from '@/stores/auth';

interface AccountSection {
  key: string;
  label: string;
  icon: string;
  component: Component;
}

// L'ordre suit la fréquence d'usage. `?tab=` reste la clé d'URL : les liens
// existants (checkout, suivi, e-mails) y pointent déjà.
const SECTIONS: AccountSection[] = [
  { key: 'overview', label: "Vue d'ensemble", icon: 'ph:house', component: AccountOverview },
  { key: 'orders', label: 'Commandes', icon: 'ph:receipt', component: AccountOrders },
  { key: 'quotes', label: 'Devis', icon: 'ph:file-text', component: AccountQuotes },
  { key: 'wishlist', label: 'Favoris et alertes', icon: 'ph:heart', component: AccountWishlist },
  { key: 'addresses', label: 'Adresses', icon: 'ph:map-pin', component: AccountAddresses },
  { key: 'profile', label: 'Profil et sécurité', icon: 'ph:user', component: AccountProfile },
  {
    key: 'preferences',
    label: 'Préférences',
    icon: 'ph:sliders-horizontal',
    component: AccountPreferences,
  },
  { key: 'group', label: 'Groupe tarifaire', icon: 'ph:seal-check', component: AccountGroup },
];

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const ready = ref(false);
const profile = ref<MyProfile | null>(null);

const current = computed<AccountSection>(() => {
  const tab = route.query.tab;
  return SECTIONS.find((s) => s.key === tab) ?? SECTIONS[0]!;
});

const firstName = computed(() => (profile.value?.full_name ?? '').trim().split(/\s+/)[0] ?? '');

useMeta(() => ({ title: `${current.value.label} | Mon compte` }));

function onProfileUpdated(updated: MyProfile) {
  profile.value = updated;
}

async function onLogout() {
  await authStore.logout();
  await router.replace({ name: 'home' });
}

onMounted(async () => {
  if (!authStore.isAuthenticated) {
    await router.replace({ name: 'login', query: { redirect: route.fullPath } });
    return;
  }
  ready.value = true;
  profile.value = await getMyProfile().catch(() => null);
});
</script>

<style scoped lang="scss">
.account__head {
  margin-bottom: 32px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.account__greeting {
  margin: 8px 0 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 15px;
  color: var(--n-ink-2);
}

.account__email {
  color: var(--n-ink-3);
}

.account__logout {
  color: var(--n-ink-2);
}

.account__layout {
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
  gap: 56px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
  }
}

.account-nav {
  position: sticky;
  top: 88px;
  display: flex;
  flex-direction: column;
  gap: 2px;

  @media (max-width: 1023px) {
    position: static;
    flex-direction: row;
    gap: 6px;
    margin: 0 -16px;
    padding: 0 16px 4px;
    overflow-x: auto;
    scrollbar-width: none;
    border-bottom: 1px solid var(--n-line);
  }
}

.account-nav__link {
  min-height: 40px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: 8px;
  color: var(--n-ink-2);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;

  &:hover {
    background: var(--n-tile);
    color: var(--n-ink);
  }

  &[aria-current='page'] {
    background: var(--n-tile);
    color: var(--n-ink);

    .account-nav__icon {
      color: var(--n-accent);
    }
  }

  @media (max-width: 1023px) {
    min-height: 44px;
    border-radius: 0;
    border-bottom: 2px solid transparent;

    &:hover,
    &[aria-current='page'] {
      background: transparent;
    }

    &[aria-current='page'] {
      border-bottom-color: var(--n-ink);
    }
  }
}

.account-nav__icon {
  color: var(--n-ink-3);
}
</style>
