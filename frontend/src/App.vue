<template>
  <router-view />
</template>

<script setup lang="ts">
import { onMounted } from 'vue';

// Marks the end of hydration: inputs filled before it are reset by Vue, so the
// e2e suite waits for this before interacting with the page.
onMounted(() => {
  document.documentElement.dataset.hydrated = 'true';
});
</script>
