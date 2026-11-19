<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">{{ $t('homepage.preview_title') }}</h2>
      </q-card-section>
      <q-card-section class="q-gutter-sm">
        <p class="admin-hint q-ma-none">{{ $t('homepage.preview_hint') }}</p>
        <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
        <q-input
          v-model="at"
          type="datetime-local"
          stack-label
          outlined
          dense
          clearable
          :label="$t('homepage.preview_date')"
          :hint="$t('homepage.preview_date_hint')"
          data-testid="preview-date"
        />
        <q-option-group
          v-model="audience"
          :options="[
            { label: $t('homepage.scope_guest'), value: 'guest' },
            { label: $t('homepage.scope_customer'), value: 'customer' },
          ]"
          inline
        />
        <q-select
          v-if="audience === 'customer'"
          v-model="groupId"
          :options="groupOptions"
          emit-value
          map-options
          clearable
          outlined
          dense
          :label="$t('homepage.preview_group')"
        />
      </q-card-section>
      <q-card-actions align="right" class="app-dialog__actions">
        <q-btn flat no-caps :label="$t('common.cancel')" @click="emit('update:modelValue', false)" />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:arrow-square-out"
          :label="$t('homepage.preview_open')"
          :loading="opening"
          data-testid="preview-open"
          @click="open"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import { fromShopDateTimeInput } from '@app/utils';

import { extractApiError } from '@/api/errors';
import { createPreviewLink, previewUrl } from '@/api/homepage';

const props = defineProps<{
  modelValue: boolean;
  groups: { id: string; label: string }[];
}>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
const { t } = useI18n();

const at = ref<string | null>(null);
const audience = ref<'guest' | 'customer'>('guest');
const groupId = ref<string | null>(null);
const opening = ref(false);
const error = ref<string | null>(null);
const groupOptions = computed(() => props.groups.map((g) => ({ label: g.label, value: g.id })));

async function open() {
  error.value = null;
  // Opened before the call: a popup blocker lets a window opened by the click
  // through, not one opened after an await.
  const tab = window.open('', '_blank');
  opening.value = true;
  try {
    const link = await createPreviewLink();
    const url = previewUrl(link, {
      at: fromShopDateTimeInput(at.value),
      customer: audience.value === 'customer',
      priceGroupId: groupId.value,
    });
    if (tab) {
      tab.opener = null;
      tab.location.href = url;
    } else {
      window.open(url, '_blank', 'noopener');
    }
    emit('update:modelValue', false);
  } catch (err) {
    tab?.close();
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    opening.value = false;
  }
}
</script>
