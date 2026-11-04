<template>
  <div class="lang-tabs" data-testid="content-language-tabs">
    <q-btn-toggle
      :model-value="modelValue"
      :options="options"
      no-caps
      dense
      unelevated
      toggle-color="primary"
      class="lang-tabs__toggle"
      @update:model-value="(value: string) => emit('update:modelValue', value)"
    />
    <div class="lang-tabs__hint">
      <template v-if="modelValue === source">
        <span class="text-subtle">{{ $t('translations.source_hint') }}</span>
      </template>
      <template v-else-if="status === 'stale' && !reviewed">
        <span class="lang-tabs__stale">{{ $t('translations.stale_hint') }}</span>
        <q-btn
          flat
          dense
          no-caps
          size="sm"
          icon="ph:check"
          :label="$t('translations.mark_reviewed')"
          data-testid="translation-mark-reviewed"
          @click="emit('review')"
        />
      </template>
      <template v-else-if="status === 'missing'">
        <span class="text-subtle">{{ $t('translations.missing_hint') }}</span>
      </template>
      <template v-else>
        <span class="text-subtle">{{ $t('translations.ok_hint') }}</span>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * Language tabs above the translatable fields of a form (R9 / T3): the source
 * language first, then every language the shop offers, each with its state
 * (translated, to review because the source changed, missing).
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

import { LOCALE_LABELS } from '@/i18n/locale';

const props = defineProps<{
  modelValue: string;
  source: string;
  locales: string[];
  /** `statusOf(lang)` of `useContentTranslations`. */
  statusOf: (code: string) => string;
  /** The current translation was marked as reviewed in this form. */
  reviewed?: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: string]; review: [] }>();

const { t } = useI18n();

const ICONS: Record<string, string> = {
  ok: 'ph:check-circle',
  stale: 'ph:warning-circle',
  missing: 'ph:circle-dashed',
};

function labelOf(code: string): string {
  return (LOCALE_LABELS as Record<string, string>)[code] ?? code.toUpperCase();
}

interface TabOption {
  value: string;
  label: string;
  icon?: string;
  'aria-label'?: string;
}

const options = computed<TabOption[]>(() =>
  props.locales.map((code) => {
    const state = props.statusOf(code);
    const base: TabOption = { value: code, label: labelOf(code) };
    if (code === props.source) return base;
    const effective = state === 'stale' && props.reviewed ? 'ok' : state;
    return {
      ...base,
      icon: ICONS[effective] ?? 'ph:circle-dashed',
      'aria-label': `${labelOf(code)} — ${t(`translations.st_${effective}`)}`,
    };
  }),
);

const status = computed(() => props.statusOf(props.modelValue));
</script>

<style scoped lang="scss">
.lang-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 16px;
  margin-bottom: 8px;
}

.lang-tabs__toggle {
  border: 1px solid var(--n-border);
  border-radius: var(--n-radius);
}

.lang-tabs__hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.lang-tabs__stale {
  color: var(--n-warn, #a15c00);
}
</style>
