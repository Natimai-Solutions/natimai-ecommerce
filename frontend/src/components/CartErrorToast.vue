<template>
  <!-- Fixed at the bottom of the screen (U8): the card clicked may be far
       from wherever a notice sits in the page. Above the compare bar. -->
  <div v-if="modelValue" class="cart-toast" role="alert" data-testid="cart-error-toast">
    <AppNotice tone="error">
      {{ modelValue }}
      <template #action>
        <q-btn
          flat
          round
          dense
          icon="ph:x"
          :aria-label="$t('common.close')"
          @click="emit('update:modelValue', null)"
        />
      </template>
    </AppNotice>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';

const props = defineProps<{ modelValue: string | null }>();
const emit = defineEmits<{ 'update:modelValue': [value: string | null] }>();

// Long enough to read, then gone: nothing asks the customer to close it.
const VISIBLE_MS = 8000;
let timer: ReturnType<typeof setTimeout> | null = null;
function stop() {
  if (timer !== null) clearTimeout(timer);
  timer = null;
}
watch(
  () => props.modelValue,
  (message) => {
    stop();
    if (message) timer = setTimeout(() => emit('update:modelValue', null), VISIBLE_MS);
  },
);
onBeforeUnmount(stop);
</script>

<style scoped lang="scss">
.cart-toast {
  position: fixed;
  left: 16px;
  right: 16px;
  // Clear of the compare bar when it shows (same place, lower layer).
  bottom: 88px;
  z-index: 2500;
  max-width: 560px;
  margin: 0 auto;
  box-shadow: var(--n-shadow);
}
</style>
