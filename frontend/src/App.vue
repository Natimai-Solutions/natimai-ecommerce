<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useMeta } from 'quasar';
import { useI18n } from 'vue-i18n';
import { useShopModulesStore } from '@/stores/shopModules';

// <html lang> follows the interface language, server render included.
const { locale } = useI18n({ useScope: 'global' });
// The site icon chosen in the back-office (R9 / T9) replaces the bundled
// favicons; without one, index.html's static links stay.
const shop = useShopModulesStore();
useMeta(() => {
  const icon = shop.config.branding?.icon;
  const link: Record<string, Record<string, string>> = {};
  if (icon) {
    link['icon16'] = {
      rel: 'icon',
      type: 'image/png',
      sizes: '16x16',
      href: `${icon.base}/icon-16.png`,
    };
    link['icon32'] = {
      rel: 'icon',
      type: 'image/png',
      sizes: '32x32',
      href: `${icon.base}/icon-32.png`,
    };
    link['apple'] = {
      rel: 'apple-touch-icon',
      sizes: '180x180',
      href: `${icon.base}/icon-180.png`,
    };
    link['manifest'] = { rel: 'manifest', href: icon.manifest };
  }
  return { htmlAttr: { lang: locale.value }, link };
});

// Marks the end of hydration: inputs filled before it are reset by Vue, so the
// e2e suite waits for this before interacting with the page.
onMounted(() => {
  document.documentElement.dataset.hydrated = 'true';
});
</script>
