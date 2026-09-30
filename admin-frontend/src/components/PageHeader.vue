<template>
  <header class="page-header">
    <div class="page-header__main">
      <router-link v-if="back" :to="back.to" class="page-header__back">
        <q-icon name="ph:arrow-left" size="16px" />
        {{ back.label }}
      </router-link>
      <div class="page-header__title-row">
        <h1 class="page-header__title" data-testid="page-title">{{ title }}</h1>
        <slot name="tags" />
      </div>
      <p v-if="hint || $slots.hint" class="page-header__hint">
        <slot name="hint">{{ hint }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router';

/**
 * En-tête commun des écrans d'administration : titre, phrase d'aide
 * facultative, retour vers la liste parente et actions principales à droite.
 */
defineProps<{
  title: string;
  hint?: string | undefined;
  back?: { to: RouteLocationRaw; label: string } | undefined;
}>();
</script>

<style scoped lang="scss">
.page-header {
  margin-bottom: 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px 24px;
}

.page-header__main {
  flex: 1 1 320px;
  min-width: 0;
}

.page-header__back {
  margin-bottom: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--n-ink-2);
  text-decoration: none;

  &:hover {
    color: var(--n-accent);
  }
}

.page-header__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.page-header__title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
}

.page-header__hint {
  max-width: 88ch;
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--n-ink-2);
}

.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
</style>
