<template>
  <div class="rich-text">
    <div v-if="label" class="rich-text__label">{{ label }}</div>
    <q-editor
      ref="editorRef"
      :model-value="modelValue"
      :min-height="minHeight"
      :toolbar="toolbar"
      :definitions="definitions"
      @update:model-value="(value: string) => emit('update:modelValue', value)"
    />
    <MediaPicker v-model="pickerOpen" :kind="mediaKind" @select="insertImage" />
  </div>
</template>

<script setup lang="ts">
/**
 * Éditeur HTML de l'admin (pages du site, description longue des produits) :
 * mise en forme simple, liens, images de la médiathèque insérées au curseur.
 * Le HTML est nettoyé à l'affichage par la vitrine (DOMPurify).
 */
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QEditor } from 'quasar';

import MediaPicker from '@/components/MediaPicker.vue';
import type { MediaAsset, MediaKind } from '@/api/media';

withDefaults(
  defineProps<{
    modelValue: string;
    label?: string;
    minHeight?: string;
    mediaKind?: MediaKind;
  }>(),
  { minHeight: '12rem', mediaKind: 'page' },
);
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();

const { t } = useI18n();
const editorRef = ref<QEditor | null>(null);
const pickerOpen = ref(false);

const toolbar = computed(() => [
  ['bold', 'italic', 'underline'],
  [{ label: t('pages.heading'), icon: 'title', list: 'no-icons', options: ['h2', 'h3', 'p'] }],
  ['unordered', 'ordered'],
  ['link', 'image', 'hr'],
  ['undo', 'redo'],
]);

const definitions = computed(() => ({
  image: {
    tip: t('pages.insert_image'),
    icon: 'image',
    label: t('pages.image'),
    handler: () => {
      // La position du curseur est gardée pour y insérer l'image au retour.
      editorRef.value?.caret.savePosition();
      pickerOpen.value = true;
    },
  },
}));

function escapeAttribute(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function insertImage(asset: MediaAsset) {
  const html =
    `<img src="${escapeAttribute(asset.url)}" srcset="${escapeAttribute(asset.srcset)}" ` +
    `sizes="(max-width: 767px) 100vw, 720px" width="${asset.width}" height="${asset.height}" ` +
    `alt="${escapeAttribute(asset.alt ?? '')}" loading="lazy">`;
  const editor = editorRef.value;
  if (!editor) return;
  editor.focus();
  editor.caret.restorePosition();
  editor.runCmd('insertHTML', html);
}
</script>

<style scoped lang="scss">
.rich-text__label {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--n-ink-3);
}
</style>
