<template>
  <q-expansion-item
    :model-value="open"
    class="app-panel help-panel"
    dense-toggle
    :icon="icon"
    :label="title"
    header-class="help-panel__head"
    @update:model-value="toggle"
  >
    <div class="help-panel__body">
      <ol
        v-if="items.length"
        class="help-panel__items"
        :class="{ 'help-panel__items--steps': steps }"
      >
        <li v-for="(item, index) in items" :key="index" class="help-panel__item">
          <span v-if="steps" class="help-panel__step font-mono" aria-hidden="true">{{
            index + 1
          }}</span>
          <q-icon v-else-if="item.icon" :name="item.icon" size="20px" class="text-muted" />
          <div>
            <div class="text-weight-medium">
              {{ item.title }}
              <span v-if="item.current" class="help-panel__here">{{
                $t('common.this_screen')
              }}</span>
            </div>
            <div class="text-caption text-muted">{{ item.text }}</div>
          </div>
        </li>
      </ol>
      <div v-if="$slots.default" class="text-caption">
        <slot />
      </div>
    </div>
  </q-expansion-item>
</template>

<script setup lang="ts">
/**
 * Encart d'explication repliable, en tête d'un écran : les notions de
 * l'écran (icône + titre + texte) ou les étapes d'un parcours (numérotées).
 *
 * Ouvert par défaut ; avec `storageKey`, un encart fermé le reste dans ce
 * navigateur. Avec `v-model`, la page décide (ex. ouvert tant que la liste
 * est vide) et rien n'est mémorisé.
 */
import { ref, watch } from 'vue';

export interface HelpItem {
  title: string;
  text: string;
  icon?: string;
  /** Étape traitée par l'écran courant (encart partagé entre plusieurs écrans). */
  current?: boolean;
}

const props = withDefaults(
  defineProps<{
    title: string;
    items?: HelpItem[];
    /** Étapes numérotées plutôt qu'icônes. */
    steps?: boolean;
    icon?: string;
    /** Mémorise le repli (localStorage) sous cette clé. */
    storageKey?: string | undefined;
    defaultOpen?: boolean;
    modelValue?: boolean | undefined;
  }>(),
  {
    items: () => [],
    steps: false,
    icon: 'ph:lightbulb',
    storageKey: undefined,
    defaultOpen: true,
    modelValue: undefined,
  },
);
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();

const STORAGE_PREFIX = 'admin.help.closed.';

function readClosed(): boolean {
  if (!props.storageKey) return false;
  try {
    return localStorage.getItem(STORAGE_PREFIX + props.storageKey) === '1';
  } catch {
    return false;
  }
}

function remember(isOpen: boolean) {
  if (!props.storageKey || props.modelValue !== undefined) return;
  try {
    if (isOpen) localStorage.removeItem(STORAGE_PREFIX + props.storageKey);
    else localStorage.setItem(STORAGE_PREFIX + props.storageKey, '1');
  } catch {
    // Stockage indisponible (navigation privée) : l'encart n'est pas mémorisé.
  }
}

const open = ref(props.modelValue ?? (readClosed() ? false : props.defaultOpen));
watch(
  () => props.modelValue,
  (value) => {
    if (value !== undefined) open.value = value;
  },
);

function toggle(value: boolean) {
  open.value = value;
  remember(value);
  emit('update:modelValue', value);
}
</script>

<style scoped lang="scss">
.help-panel {
  margin-bottom: 16px;
}

.help-panel :deep(.help-panel__head) {
  font-weight: 500;
}

.help-panel__body {
  display: grid;
  gap: 14px;
  padding: 4px 16px 16px;
}

.help-panel__items {
  display: grid;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.help-panel__item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  line-height: 1.45;
}

.help-panel__here {
  margin-left: 6px;
  padding: 1px 8px;
  border: 1px solid var(--n-line-2);
  border-radius: var(--n-radius-pill);
  font-size: 11px;
  font-weight: 500;
  color: var(--n-ink-2);
  vertical-align: 1px;
}

.help-panel__step {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--n-radius-pill);
  background: var(--n-ink);
  color: var(--n-surface);
  font-size: 12px;
}
</style>
