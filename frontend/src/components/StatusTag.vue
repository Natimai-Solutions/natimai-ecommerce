<template>
  <span class="status-tag" :class="`status-tag--${tone}`">
    <q-icon v-if="icon" :name="icon" size="14px" class="status-tag__icon" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import type { StatusTone } from 'src/utils/statusTone';

/**
 * Étiquette d'état : pilule neutre, seule l'icône porte la couleur de l'état
 * (validé, en attente, refusé). Remplace les q-chip remplis de couleur vive.
 */
withDefaults(defineProps<{ label: string; tone?: StatusTone; icon?: string }>(), {
  tone: 'neutral',
});
</script>

<style scoped lang="scss">
.status-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--n-line-2);
  border-radius: 999px;
  color: var(--n-ink);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;

  & + & {
    margin-left: 6px;
  }
}

.status-tag__icon {
  color: var(--n-ink-3);

  .status-tag--ok & {
    color: var(--n-ok);
  }

  .status-tag--warn & {
    color: var(--n-warn);
  }

  .status-tag--danger & {
    color: var(--n-danger);
  }
}
</style>
