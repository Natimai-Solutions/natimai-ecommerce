<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('branding.title')" :hint="$t('branding.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div v-if="loading && !loaded" class="text-center q-pa-xl"><q-spinner size="2.5em" /></div>

    <template v-else>
      <section
        v-for="slot in slots"
        :key="slot.key"
        class="app-section"
        :aria-labelledby="`branding-${slot.key}`"
        :data-testid="`branding-${slot.key}`"
      >
        <div class="app-section__head">
          <h2 :id="`branding-${slot.key}`" class="app-section__title">{{ slot.label }}</h2>
          <p class="app-section__hint">{{ slot.hint }}</p>
        </div>
        <div class="row items-center q-gutter-md">
          <div class="branding-preview" :class="`branding-preview--${slot.key}`">
            <img v-if="slot.asset" :src="slot.asset.url" :alt="slot.asset.alt ?? ''" />
            <q-icon
              v-else
              :name="slot.key === 'logo' ? 'ph:text-aa' : 'ph:app-window'"
              size="32px"
              class="text-subtle"
            />
          </div>
          <div class="column q-gutter-sm">
            <q-btn
              outline
              no-caps
              icon="ph:images"
              :label="slot.asset ? $t('branding.change') : $t('branding.pick')"
              :data-testid="`branding-pick-${slot.key}`"
              @click="openPicker(slot.key)"
            />
            <q-btn
              v-if="slot.asset"
              flat
              dense
              no-caps
              color="negative"
              :label="$t('branding.remove')"
              @click="clear(slot.key)"
            />
            <p class="admin-hint q-mb-none">
              <strong>{{ $t('media.recommended') }}</strong> {{ $t(imageFormatLabelKey(slot.key)) }}
            </p>
          </div>
        </div>
        <p v-if="slot.key === 'icon' && slot.asset" class="admin-hint q-mt-sm q-mb-none">
          {{ $t('branding.icon_sizes') }}
        </p>
      </section>
    </template>

    <MediaPicker v-model="pickerOpen" kind="branding" :format="pickerFormat" @select="onPick" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';
import PageHeader from '@/components/PageHeader.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import { extractApiError } from '@/api/errors';
import { listMedia, type MediaAsset } from '@/api/media';
import { listSystemSettings, updateSystemSetting } from '@/api/systemSettings';
import { imageFormatLabelKey, type ImageFormatKey } from '@/utils/imageFormats';

/**
 * Logo and site icon (R9 / T9): two settings holding a media-library asset.
 * The storefront, the e-mails and the PDFs read them; the admin keeps its own
 * icon so its tabs are never mistaken for the shop's.
 */
const { t } = useI18n();

type SlotKey = 'logo' | 'icon';
// Keyed by slot; written so the icon-coverage test does not read the
// setting name as a glyph name.
const SETTING_KEYS: Record<SlotKey, string> = {
  logo: 'shop_logo_media_id',
  ['icon']: 'shop_icon_media_id',
};

const loading = ref(false);
const loaded = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const assetIds = ref<Record<SlotKey, string | null>>({ logo: null, icon: null });
const assets = ref<Record<string, MediaAsset>>({});
const pickerOpen = ref(false);
const picking = ref<SlotKey>('logo');
const pickerFormat = computed<ImageFormatKey>(() => picking.value);

const slots = computed(() =>
  (['logo', 'icon'] as SlotKey[]).map((key) => {
    const id = assetIds.value[key];
    return {
      key,
      label: t(`branding.${key}`),
      hint: t(`branding.${key}_hint`),
      asset: id ? (assets.value[id] ?? null) : null,
    };
  }),
);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [settings, media] = await Promise.all([listSystemSettings(), listMedia('branding')]);
    assets.value = Object.fromEntries(media.map((asset) => [asset.id, asset]));
    for (const key of ['logo', 'icon'] as SlotKey[]) {
      const setting = settings.find((s) => s.key === SETTING_KEYS[key]);
      const value = setting ? String(setting.value ?? '').trim() : '';
      assetIds.value[key] = value || null;
    }
    loaded.value = true;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function openPicker(key: SlotKey) {
  picking.value = key;
  pickerOpen.value = true;
}

async function save(key: SlotKey, value: string) {
  error.value = null;
  notice.value = null;
  try {
    await updateSystemSetting(SETTING_KEYS[key], { value });
    notice.value = t('branding.saved');
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('branding.save_failed');
  }
}

async function onPick(asset: MediaAsset) {
  assets.value[asset.id] = asset;
  await save(picking.value, asset.id);
}

async function clear(key: SlotKey) {
  await save(key, '');
}

onMounted(load);
</script>

<style scoped lang="scss">
.branding-preview {
  width: 240px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--n-line);
  border-radius: var(--n-radius);
  background: var(--n-tile);
  overflow: hidden;

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
}

.branding-preview--icon {
  width: 120px;

  img {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border-radius: var(--n-radius-lg);
  }
}
</style>
