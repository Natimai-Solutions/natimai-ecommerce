<template>
  <span class="status-tag" :class="`status-tag--${tone}`">
    <q-icon v-if="icon" :name="icon" size="14px" class="status-tag__icon" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import type { StatusTone } from './statusTone';

/**
 * Étiquette d'état : pilule neutre, seule l'icône porte la couleur de l'état
 * (validé, en attente, refusé). Remplace les q-chip remplis de couleur vive.
 */
withDefaults(defineProps<{ label: string; tone?: StatusTone; icon?: string }>(), {
  tone: 'neutral',
});
</script>

<style scoped>
/* CSS simple (pas de SCSS) : voir AppNotice.vue. */
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--n-line-2);
  border-radius: var(--n-radius-pill);
  color: var(--n-ink);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}

.status-tag + .status-tag {
  margin-left: 6px;
}

.status-tag__icon {
  color: var(--n-ink-3);
}

.status-tag--ok .status-tag__icon {
  color: var(--n-ok);
}

.status-tag--warn .status-tag__icon {
  color: var(--n-warn);
}

.status-tag--danger .status-tag__icon {
  color: var(--n-danger);
}
</style>
