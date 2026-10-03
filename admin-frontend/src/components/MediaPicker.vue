<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog app-dialog--xl">
      <q-card-section class="app-dialog__head">
        <div class="row items-center no-wrap">
          <h2 class="app-dialog__title col">{{ $t('media.title') }}</h2>
          <q-btn flat round dense icon="ph:x" :aria-label="$t('media.close')" v-close-popup />
        </div>
      </q-card-section>

      <q-card-section>
        <div class="row q-col-gutter-sm items-start">
          <q-file
            v-model="file"
            class="col-12 col-md-5"
            :label="$t('media.new')"
            accept="image/jpeg,image/png,image/webp"
            outlined
            dense
            clearable
            data-testid="media-file"
          >
            <template #prepend><q-icon name="ph:image" /></template>
          </q-file>
          <q-input v-model="alt" class="col-12 col-md-4" :label="$t('media.alt')" outlined dense />
          <div class="col-12 col-md-3">
            <q-btn
              color="primary"
              unelevated
              no-caps
              icon="ph:cloud-arrow-up"
              :label="$t('media.upload')"
              class="full-width"
              :disable="!file"
              :loading="uploading"
              data-testid="media-upload"
              @click="upload"
            />
          </div>
        </div>
        <p class="admin-hint q-mt-xs q-mb-none" data-testid="media-format-hint">
          <strong>{{ $t('media.recommended') }}</strong> {{ $t(imageFormatLabelKey(format)) }}
        </p>
        <p class="admin-hint q-mt-xs q-mb-none">
          {{ $t('media.upload_hint') }}
        </p>

        <AppNotice v-if="error" tone="error" dense class="q-mt-sm">{{ error }}</AppNotice>

        <div class="row items-center q-mt-md q-gutter-xs">
          <q-btn
            v-for="option in kindOptions"
            :key="option.value ?? 'all'"
            dense
            no-caps
            unelevated
            :outline="filter !== option.value"
            color="primary"
            :label="option.label"
            @click="setFilter(option.value)"
          />
        </div>
      </q-card-section>

      <q-card-section class="media-picker__grid-wrap">
        <div v-if="loading" class="row justify-center q-pa-lg">
          <q-spinner size="2em" />
        </div>
        <div v-else-if="!assets.length" class="app-empty">
          <q-icon name="ph:images" size="28px" class="text-subtle" />
          <h3>{{ $t('media.none') }}</h3>
          <p>{{ $t('media.none_hint') }}</p>
        </div>
        <div v-else class="media-picker__grid">
          <button
            v-for="asset in assets"
            :key="asset.id"
            type="button"
            class="media-tile"
            :class="{ 'media-tile--selected': selected?.id === asset.id }"
            :aria-pressed="selected?.id === asset.id"
            @click="selected = asset"
            @dblclick="confirm(asset)"
          >
            <img :src="thumbnail(asset)" :alt="asset.alt ?? ''" loading="lazy" />
            <span class="media-tile__meta">
              {{ asset.width }} × {{ asset.height }}
              <template v-if="asset.alt"> · {{ asset.alt }}</template>
            </span>
          </button>
        </div>
      </q-card-section>

      <q-card-section v-if="selected" class="media-picker__edit" data-testid="media-edit">
        <q-input
          v-model="editAlt"
          :label="$t('media.alt_edit')"
          :hint="$t('media.alt_edit_hint')"
          outlined
          dense
          bottom-slots
          class="col"
          data-testid="media-edit-alt"
          @keyup.enter="saveAlt"
        >
          <template #append>
            <q-btn
              flat
              dense
              no-caps
              :label="$t('media.alt_save')"
              :disable="editAlt.trim() === (selected.alt ?? '')"
              :loading="savingAlt"
              data-testid="media-edit-save"
              @click="saveAlt"
            />
          </template>
        </q-input>
      </q-card-section>

      <q-card-actions align="right" class="app-dialog__actions">
        <q-btn
          v-if="selected"
          flat
          no-caps
          color="negative"
          icon="ph:trash"
          :label="$t('common.delete')"
          :loading="deleting"
          @click="remove(selected)"
        />
        <q-space />
        <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
        <q-btn
          color="primary"
          unelevated
          no-caps
          :label="$t('media.use')"
          :disable="!selected"
          data-testid="media-confirm"
          @click="selected && confirm(selected)"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, ref, watch } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import { extractApiError } from '@/api/errors';
import { useConfirm } from '@/composables/useConfirm';
import { formatForKind, imageFormatLabelKey, type ImageFormatKey } from '@/utils/imageFormats';
import {
  deleteMedia,
  listMedia,
  MEDIA_KIND_LABELS,
  updateMedia,
  uploadMedia,
  type MediaAsset,
  type MediaKind,
} from '@/api/media';

const { t } = useI18n();
const { confirmDelete } = useConfirm();

/**
 * Médiathèque partagée : accueil, produits, catégories, pages. Ouvre la liste
 * des images (filtrée par usage), en téléverse une nouvelle et renvoie celle
 * choisie via `select`.
 */
const props = withDefaults(
  defineProps<{ modelValue: boolean; kind?: MediaKind; format?: ImageFormatKey | null }>(),
  { kind: 'other', format: null },
);
/** The recommended format: the caller's (a hero vs a banner), else the kind's. */
const format = computed<ImageFormatKey>(() => props.format ?? formatForKind(props.kind));
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  select: [asset: MediaAsset];
  /** The alt text (or kind) of an image was changed in the library. */
  updated: [asset: MediaAsset];
}>();

const assets = ref<MediaAsset[]>([]);
const loading = ref(false);
const uploading = ref(false);
const deleting = ref(false);
const error = ref<string | null>(null);
const file = ref<File | null>(null);
const alt = ref('');
const selected = ref<MediaAsset | null>(null);
// The selected image's alt text, editable after the upload (03/10/2026).
const editAlt = ref('');
const savingAlt = ref(false);
watch(selected, (asset) => {
  editAlt.value = asset?.alt ?? '';
});
const filter = ref<MediaKind | null>(props.kind);

const kindOptions = computed<{ label: string; value: MediaKind | null }[]>(() => [
  ...(Object.entries(MEDIA_KIND_LABELS) as [MediaKind, string][]).map(([value, label]) => ({
    value,
    label,
  })),
  { label: t('media.all'), value: null },
]);

function thumbnail(asset: MediaAsset): string {
  return asset.variants?.[0]?.url ?? asset.url;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    assets.value = await listMedia(filter.value);
  } catch (err) {
    error.value = extractApiError(err) ?? t('media.load_failed');
  } finally {
    loading.value = false;
  }
}

function setFilter(value: MediaKind | null) {
  filter.value = value;
  void load();
}

async function upload() {
  if (!file.value) return;
  uploading.value = true;
  error.value = null;
  try {
    const asset = await uploadMedia(file.value, props.kind, alt.value.trim() || null);
    file.value = null;
    alt.value = '';
    filter.value = props.kind;
    await load();
    selected.value = assets.value.find((a) => a.id === asset.id) ?? asset;
  } catch (err) {
    error.value = extractApiError(err) ?? t('media.upload_failed');
  } finally {
    uploading.value = false;
  }
}

async function remove(asset: MediaAsset) {
  if (!(await confirmDelete(asset.alt || asset.original_filename || t('media.this_image')))) return;
  deleting.value = true;
  error.value = null;
  try {
    await deleteMedia(asset.id);
    selected.value = null;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  } finally {
    deleting.value = false;
  }
}

async function saveAlt() {
  const asset = selected.value;
  if (!asset || savingAlt.value) return;
  savingAlt.value = true;
  error.value = null;
  try {
    const updated = await updateMedia(asset.id, { alt: editAlt.value.trim() || null });
    assets.value = assets.value.map((a) => (a.id === updated.id ? updated : a));
    selected.value = updated;
    emit('updated', updated);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    savingAlt.value = false;
  }
}

function confirm(asset: MediaAsset) {
  emit('select', asset);
  emit('update:modelValue', false);
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    selected.value = null;
    filter.value = props.kind;
    void load();
  },
);
</script>

<style scoped lang="scss">
.media-picker__grid-wrap {
  max-height: 55vh;
  overflow-y: auto;
}

.media-picker__edit {
  padding-top: 0;
}

.media-picker__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}

.media-tile {
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 2px solid transparent;
  border-radius: 8px;
  background: none;
  text-align: left;
  cursor: pointer;

  img {
    width: 100%;
    aspect-ratio: 4 / 3;
    object-fit: cover;
    border-radius: 6px;
    background: var(--n-tile);
  }

  &--selected {
    border-color: var(--n-accent);
  }
}

.media-tile__meta {
  padding: 0 4px 4px;
  font-size: 12px;
  color: var(--n-ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
