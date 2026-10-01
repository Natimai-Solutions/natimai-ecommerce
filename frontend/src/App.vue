<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useMeta } from 'quasar';
import { useI18n } from 'vue-i18n';

// <html lang> follows the interface language, server render included.
const { locale } = useI18n({ useScope: 'global' });
useMeta(() => ({ htmlAttr: { lang: locale.value } }));

// Marks the end of hydration: inputs filled before it are reset by Vue, so the
// e2e suite waits for this before interacting with the page.
onMounted(() => {
  document.documentElement.dataset.hydrated = 'true';
});
</script>
