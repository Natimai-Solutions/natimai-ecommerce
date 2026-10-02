<template>
  <main class="not-found">
    <span class="not-found__code font-mono">404</span>
    <h1 class="not-found__title">{{ $t('not_found.title') }}</h1>
    <p class="not-found__text">{{ $t('not_found.text') }}</p>
    <q-btn unelevated color="primary" :label="$t('not_found.see_catalogue')" to="/catalogue" />
  </main>
</template>

<style scoped lang="scss">
.not-found {
  min-height: 100dvh;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-align: center;
  background: var(--n-bg);
  color: var(--n-ink);
}

.not-found__code {
  font-size: 14px;
  color: var(--n-ink-3);
}

.not-found__title {
  margin: 0;
  font-size: 32px;
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.025em;
}

.not-found__text {
  max-width: 44ch;
  margin: 0 0 16px;
  color: var(--n-ink-2);
}

.q-btn {
  min-height: 48px;
  padding: 0 24px;
}
</style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { usePageMeta } from '@/composables/usePageMeta';

const { t } = useI18n();
usePageMeta(() => ({ title: t('not_found.title'), noindex: true }));
</script>
