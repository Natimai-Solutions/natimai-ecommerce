<template>
  <div class="choice-list" role="radiogroup" :aria-label="label">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      class="choice"
      :class="{ 'choice--selected': option.value === modelValue }"
      :aria-checked="option.value === modelValue"
      :disabled="disabled || option.disabled"
      :data-testid="option.testid"
      @click="emit('update:modelValue', option.value)"
    >
      <span class="choice__mark" aria-hidden="true" />
      <q-icon v-if="option.icon" :name="option.icon" size="20px" class="choice__icon" />
      <span class="choice__text">
        <span class="choice__title">{{ option.title }}</span>
        <span v-if="option.caption" class="choice__caption">{{ option.caption }}</span>
      </span>
      <span v-if="option.aside || $slots.aside" class="choice__aside">
        <slot name="aside" :option="option">{{ option.aside }}</slot>
      </span>
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends string">
/**
 * Liste de choix exclusifs (adresse, mode de livraison, moyen de paiement…).
 * Chaque option est un bouton `role="radio"` entier cliquable, avec son
 * `data-testid` pour les tests de bout en bout.
 */
export interface ChoiceOption<V extends string = string> {
  value: V;
  title: string;
  caption?: string | null;
  icon?: string;
  aside?: string | null;
  testid?: string;
  disabled?: boolean;
}

defineProps<{
  modelValue: T | null;
  options: ChoiceOption<T>[];
  label: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{ 'update:modelValue': [value: T] }>();
</script>

<style scoped lang="scss">
.choice-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.choice {
  width: 100%;
  min-height: 60px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--n-line-2);
  border-radius: var(--n-radius);
  background: var(--n-surface);
  color: var(--n-ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background-color 0.2s ease;

  &:hover:not(:disabled) {
    border-color: var(--n-ink-3);
  }

  &:disabled {
    cursor: default;
    opacity: 0.55;
  }

  &--selected {
    border-color: var(--n-ink);
    box-shadow: inset 0 0 0 1px var(--n-ink);

    &:hover:not(:disabled) {
      border-color: var(--n-ink);
    }
  }
}

.choice__mark {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border: 1.5px solid var(--n-line-2);
  border-radius: var(--n-radius-pill);
  transition: border 0.15s ease;

  .choice--selected & {
    border: 5px solid var(--n-ink);
  }
}

.choice__icon {
  flex-shrink: 0;
  color: var(--n-ink-2);
}

.choice__text {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.choice__title {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.35;
}

.choice__caption {
  font-size: 13px;
  line-height: 1.4;
  color: var(--n-ink-2);
}

.choice__aside {
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}
</style>
