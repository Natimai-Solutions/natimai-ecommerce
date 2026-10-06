<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useShopConfigStore } from '@/stores/shopConfig';
import { applySiteIcon } from '@/utils/siteIcon';

// The site icon chosen in the back-office (Système → Identité visuelle) is
// the favicon of the admin too: one brand, one tab icon. Without a setting
// the bundled icons declared in index.html stay.
const shopConfig = useShopConfigStore();
onMounted(() => void shopConfig.load());
watch(
  () => shopConfig.config?.branding?.icon ?? null,
  (icon) => applySiteIcon(icon),
);
</script>
