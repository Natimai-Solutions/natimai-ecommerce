<template>
  <div
    class="app-notice"
    :class="[`app-notice--${tone}`, { 'app-notice--dense': dense }]"
    :role="tone === 'error' || tone === 'warning' ? 'alert' : 'status'"
  >
    <q-icon :name="icon ?? DEFAULT_ICONS[tone]" class="app-notice__icon" size="20px" />
    <div class="app-notice__body"><slot /></div>
    <div v-if="$slots.action" class="app-notice__action"><slot name="action" /></div>
  </div>
</template>

<script setup lang="ts">
export type NoticeTone = 'info' | 'success' | 'warning' | 'error';

withDefaults(defineProps<{ tone?: NoticeTone; icon?: string; dense?: boolean }>(), {
  tone: 'info',
  dense: false,
});

const DEFAULT_ICONS: Record<NoticeTone, string> = {
  info: 'ph:info',
  success: 'ph:check-circle',
  warning: 'ph:warning',
  error: 'ph:warning-circle',
};
</script>

<style scoped>
/* CSS simple (pas de SCSS) : Quasar injecte ses variables Sass dans chaque bloc
   SCSS, introuvables depuis ce paquet partagé. */
.app-notice {
  --notice-tone: var(--n-ink-2);

  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--notice-tone) 30%, var(--n-line));
  border-radius: 8px;
  background: color-mix(in srgb, var(--notice-tone) 6%, var(--n-surface));
  color: var(--n-ink);
  font-size: 14px;
  line-height: 1.5;
}

.app-notice--info {
  border-color: var(--n-line);
  background: var(--n-tile);
}

.app-notice--success {
  --notice-tone: var(--n-ok);
}

.app-notice--warning {
  --notice-tone: var(--n-warn);
}

.app-notice--error {
  --notice-tone: var(--n-danger);
}

.app-notice--dense {
  padding: 10px 12px;
  gap: 10px;
}

.app-notice__icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--notice-tone);
}

.app-notice__body {
  flex-grow: 1;
  min-width: 0;
}

.app-notice__action {
  flex-shrink: 0;
  margin: -6px -8px -6px 0;
}
</style>
