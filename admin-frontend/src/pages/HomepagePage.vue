<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('homepage.title')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn-dropdown
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('homepage.new')"
          data-testid="homepage-new"
        >
          <q-list dense>
            <q-item
              v-for="option in kindOptions"
              :key="option.value"
              v-close-popup
              clickable
              :data-testid="`homepage-new-${option.value}`"
              @click="openCreate(option.value)"
            >
              <q-item-section avatar><q-icon :name="kindIcon(option.value)" /></q-item-section>
              <q-item-section>{{ option.label }}</q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>
      </template>
    </PageHeader>

    <p class="admin-hint">
      <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
      <span v-html="$t('homepage.intro')"></span>
    </p>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
      <AppNotice
        v-if="liveHeroes.length > 1"
        tone="warning"
        dense
        data-testid="homepage-hero-warning"
      >
        {{
          $t('homepage.hero_conflict', { n: liveHeroes.length, shown: liveHeroes[0]?.title ?? '' })
        }}
      </AppNotice>
    </div>

    <div v-if="loading && !blocks.length" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <template v-else>
      <div v-if="!blocks.length" class="app-empty">
        <q-icon name="ph:layout" size="28px" class="text-subtle" />
        <h3>{{ $t('homepage.empty') }}</h3>
        <q-btn
          outline
          no-caps
          icon="ph:plus"
          :label="$t('homepage.add_hero')"
          @click="openCreate('hero')"
        />
      </div>
      <q-list v-else bordered separator class="rounded-borders">
        <q-item v-for="(block, index) in blocks" :key="block.id" data-testid="homepage-block">
          <q-item-section avatar>
            <img
              v-if="block.image"
              :src="block.image.src"
              alt=""
              class="homepage-thumb"
              loading="lazy"
            />
            <div v-else class="homepage-thumb homepage-thumb--empty">
              <q-icon :name="kindIcon(block.kind)" class="text-subtle" />
            </div>
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-weight-medium">
              {{ block.title || defaultTitle(block.kind) }}
            </q-item-label>
            <q-item-label caption>
              {{ kindLabel(block.kind)
              }}<template v-if="configLabel(block)"> · {{ configLabel(block) }}</template> ·
              {{ audienceLabel(block) }}
            </q-item-label>
            <q-item-label v-if="block.subtitle" caption lines="2">
              {{ block.subtitle }}
            </q-item-label>
            <q-item-label v-if="block.cta_link || block.starts_at || block.ends_at" caption>
              <template v-if="block.cta_link">
                {{ block.cta_label || $t('homepage.discover') }} → {{ block.cta_link }}
              </template>
              <template v-if="block.starts_at || block.ends_at">
                · {{ windowLabel(block) }}
              </template>
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <StatusTag
              :label="status(block).label"
              :tone="status(block).tone"
              :icon="status(block).icon"
            />
          </q-item-section>
          <q-item-section side>
            <div class="row no-wrap">
              <q-btn
                :aria-label="$t('homepage.up')"
                flat
                round
                dense
                icon="ph:arrow-up"
                :disable="index === 0 || reordering"
                @click="move(index, -1)"
              >
                <q-tooltip>{{ $t('homepage.up') }}</q-tooltip>
              </q-btn>
              <q-btn
                :aria-label="$t('homepage.down')"
                flat
                round
                dense
                icon="ph:arrow-down"
                :disable="index === blocks.length - 1 || reordering"
                @click="move(index, 1)"
              >
                <q-tooltip>{{ $t('homepage.down') }}</q-tooltip>
              </q-btn>
              <q-btn
                :aria-label="$t('common.edit')"
                flat
                round
                dense
                icon="ph:pencil-simple"
                @click="openEdit(block)"
              >
                <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
              </q-btn>
              <q-btn
                :aria-label="$t('common.delete')"
                flat
                round
                dense
                icon="ph:trash"
                color="negative"
                data-testid="homepage-delete"
                @click="remove(block)"
              >
                <q-tooltip>{{ $t('common.delete') }}</q-tooltip>
              </q-btn>
            </div>
          </q-item-section>
        </q-item>
      </q-list>
    </template>

    <q-dialog
      :model-value="dialog"
      :persistent="guard.persistent.value"
      @update:model-value="guard.onToggle"
    >
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head row items-center no-wrap q-gutter-x-sm">
          <h2 class="app-dialog__title col">
            {{ editingId ? $t('homepage.edit_title') : $t('homepage.new_title') }}
          </h2>
          <q-btn
            :aria-label="$t('common.close')"
            flat
            round
            dense
            icon="ph:x"
            @click="guard.requestClose()"
          >
            <q-tooltip>{{ $t('common.close') }}</q-tooltip>
          </q-btn>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-option-group
              v-model="form.kind"
              :options="kindOptions"
              inline
              :disable="!!editingId"
            />
            <ContentLanguageTabs
              v-model="content.lang.value"
              :source="content.source.value"
              :locales="content.locales.value"
              :status-of="content.statusOf"
              :reviewed="content.reviewed.value"
              @review="content.markReviewed"
            />
            <q-input
              v-model="texts.title"
              :label="isBuiltin ? $t('homepage.section_title') : $t('homepage.block_title')"
              :hint="
                isBuiltin
                  ? $t('homepage.section_title_hint', { title: defaultTitle(form.kind) })
                  : undefined
              "
              outlined
              dense
              maxlength="200"
              :rules="
                content.isSource.value && !isBuiltin
                  ? [(v: string) => !!v.trim() || $t('homepage.title_rule')]
                  : []
              "
              data-testid="homepage-title"
            />
            <q-input
              v-model="texts.subtitle"
              :label="$t('homepage.text')"
              type="textarea"
              autogrow
              outlined
              dense
              maxlength="500"
            />
            <div v-if="isBuiltin" class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.limit"
                class="col-12 col-sm-4"
                type="number"
                :min="2"
                :max="24"
                :label="
                  form.kind === 'categories'
                    ? $t('homepage.limit_categories')
                    : $t('homepage.limit_products')
                "
                outlined
                dense
                data-testid="homepage-limit"
              />
              <q-input
                v-if="form.kind === 'popular'"
                v-model.number="form.days"
                class="col-12 col-sm-4"
                type="number"
                :min="1"
                :max="365"
                :label="$t('homepage.days')"
                outlined
                dense
              />
            </div>
            <div v-if="!isBuiltin" class="row q-col-gutter-sm">
              <q-input
                v-model="texts.cta_label"
                class="col-12 col-sm-4"
                :label="$t('homepage.cta')"
                :hint="$t('homepage.cta_hint')"
                outlined
                dense
                maxlength="60"
              />
              <q-input
                v-model="form.cta_link"
                class="col-12 col-sm-8"
                :label="$t('homepage.link')"
                :hint="$t('homepage.link_hint')"
                outlined
                dense
                maxlength="500"
              />
            </div>

            <template v-if="!isBuiltin">
              <h3 class="admin-subtitle q-mt-md">{{ $t('homepage.image') }}</h3>
              <p class="admin-hint q-mb-sm">
                <strong>{{ $t('media.recommended') }}</strong>
                {{ $t(imageFormatLabelKey(form.kind === 'hero' ? 'hero' : 'banner')) }}
              </p>
              <div class="row items-center q-gutter-md">
                <img v-if="previewSrc" :src="previewSrc" alt="" class="homepage-preview" />
                <div v-else class="homepage-preview homepage-thumb--empty">
                  <q-icon name="ph:image" size="32px" class="text-subtle" />
                </div>
                <div class="column q-gutter-sm">
                  <q-btn
                    outline
                    no-caps
                    icon="ph:images"
                    :label="$t('homepage.pick')"
                    data-testid="homepage-pick-image"
                    @click="pickerOpen = true"
                  />
                  <q-btn
                    v-if="form.media_id || form.image_url"
                    flat
                    dense
                    no-caps
                    :label="$t('homepage.remove_image')"
                    @click="clearImage"
                  />
                </div>
              </div>
              <q-input
                v-if="!form.media_id"
                v-model="form.image_url"
                :label="$t('homepage.external')"
                outlined
                dense
                maxlength="500"
              />
              <q-input
                v-model="texts.alt"
                :label="$t('homepage.alt')"
                :hint="$t('homepage.alt_hint')"
                outlined
                dense
                maxlength="255"
              />
            </template>

            <h3 class="admin-subtitle q-mt-md">{{ $t('homepage.audience') }}</h3>
            <p class="admin-hint q-mb-sm">{{ $t('homepage.audience_hint') }}</p>
            <q-option-group
              v-model="form.scope"
              :options="[
                { label: $t('homepage.scope_all'), value: 'all' },
                { label: $t('homepage.scope_guest'), value: 'guest' },
                { label: $t('homepage.scope_customer'), value: 'customer' },
              ]"
              inline
              data-testid="homepage-scope"
            />
            <div class="row q-col-gutter-sm">
              <q-select
                v-if="form.scope === 'customer'"
                v-model="form.price_group_ids"
                class="col-12 col-sm-6"
                :options="groupOptions"
                emit-value
                map-options
                multiple
                use-chips
                outlined
                dense
                :label="$t('homepage.groups')"
                :hint="$t('homepage.groups_hint')"
                data-testid="homepage-groups"
              />
              <q-select
                v-model="form.locales"
                class="col-12 col-sm-6"
                :options="localeOptions"
                emit-value
                map-options
                multiple
                use-chips
                outlined
                dense
                :label="$t('homepage.locales')"
                :hint="$t('homepage.locales_hint')"
              />
            </div>

            <h3 class="admin-subtitle q-mt-md">{{ $t('homepage.publication') }}</h3>
            <div class="row q-col-gutter-sm items-center">
              <q-toggle
                v-model="form.is_published"
                class="col-12 col-sm-4"
                :label="$t('homepage.published')"
                data-testid="homepage-published"
              />
              <q-input
                v-model="form.starts_at"
                class="col-12 col-sm-4"
                type="datetime-local"
                :label="$t('homepage.from')"
                stack-label
                outlined
                dense
                clearable
              />
              <q-input
                v-model="form.ends_at"
                class="col-12 col-sm-4"
                type="datetime-local"
                :label="$t('homepage.until')"
                stack-label
                outlined
                dense
                clearable
              />
            </div>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="guard.requestClose()" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
              data-testid="homepage-save"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <MediaPicker
      v-model="pickerOpen"
      kind="homepage"
      :format="form.kind === 'hero' ? 'hero' : 'banner'"
      @select="onPick"
    />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';
import { formatDateTime, fromShopDateTimeInput, toShopDateTimeInput } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import { imageFormatLabelKey } from '@/utils/imageFormats';
import ContentLanguageTabs from '@/components/ContentLanguageTabs.vue';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';
import { useConfirm } from '@/composables/useConfirm';
import {
  cloneTranslations,
  useContentTranslations,
  type Translations,
} from '@/composables/useContentTranslations';
import { extractApiError } from '@/api/errors';
import {
  createHomepageBlock,
  deleteHomepageBlock,
  listHomepageBlocks,
  reorderHomepageBlocks,
  saveHomepageBlock,
  type HomepageBlock,
  type HomepageBlockWrite,
} from '@/api/homepage';
import { listPriceGroups, type PriceGroup } from '@/api/eligibility';
import { useShopConfigStore } from '@/stores/shopConfig';
import type { MediaAsset } from '@/api/media';

const { t } = useI18n();
const { confirmDelete } = useConfirm();

type Kind = 'hero' | 'banner' | 'categories' | 'featured' | 'popular';
type Scope = 'all' | 'guest' | 'customer';
const BUILTIN: Kind[] = ['categories', 'featured', 'popular'];

const blocks = ref<HomepageBlock[]>([]);
const priceGroups = ref<PriceGroup[]>([]);
const loading = ref(false);
const reordering = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const shop = useShopConfigStore();

const kindOptions = computed<{ label: string; value: Kind }[]>(() => [
  { label: t('homepage.kind_hero'), value: 'hero' },
  { label: t('homepage.kind_banner'), value: 'banner' },
  { label: t('homepage.kind_categories'), value: 'categories' },
  { label: t('homepage.kind_featured'), value: 'featured' },
  { label: t('homepage.kind_popular'), value: 'popular' },
]);

function kindLabel(kind: string): string {
  return kindOptions.value.find((o) => o.value === kind)?.label ?? kind;
}

function kindIcon(kind: string): string {
  return (
    {
      hero: 'ph:image',
      banner: 'ph:rectangle',
      categories: 'ph:squares-four',
      featured: 'ph:star',
      popular: 'ph:trend-up',
    }[kind] ?? 'ph:square'
  );
}

/** The title the storefront shows when none is typed (shop sections). */
function defaultTitle(kind: string): string {
  return (
    {
      categories: t('homepage.default_categories'),
      featured: t('homepage.default_featured'),
      popular: t('homepage.default_popular'),
    }[kind] ?? ''
  );
}

function configLabel(block: HomepageBlock): string {
  const config = (block.config ?? {}) as Record<string, number>;
  if (block.kind === 'popular') {
    return t('homepage.config_popular', { n: config['limit'] ?? 8, days: config['days'] ?? 30 });
  }
  if (BUILTIN.includes(block.kind as Kind)) {
    return t('homepage.config_limit', { n: config['limit'] ?? 8 });
  }
  return '';
}

function audienceLabel(block: HomepageBlock): string {
  const audience = (block.audience ?? {}) as {
    scope?: Scope;
    price_group_ids?: string[];
    locales?: string[];
  };
  let who =
    audience.scope === 'guest'
      ? t('homepage.scope_guest')
      : audience.scope === 'customer'
        ? t('homepage.scope_customer')
        : t('homepage.scope_all');
  if (audience.scope === 'customer' && audience.price_group_ids?.length) {
    who = audience.price_group_ids
      .map((id) => priceGroups.value.find((g) => g.id === id)?.label ?? '?')
      .join(', ');
  }
  const langs = audience.locales?.length ? ` (${audience.locales.join(', ')})` : '';
  return who + langs;
}

const groupOptions = computed(() =>
  priceGroups.value.map((g) => ({ label: g.label, value: g.id })),
);
const localeOptions = computed(() =>
  (shop.config?.available_locales ?? ['fr', 'en']).map((code: string) => ({
    label: code.toUpperCase(),
    value: code,
  })),
);

/** Heroes live right now for everyone: the storefront shows the first only. */
const liveHeroes = computed(() =>
  blocks.value.filter(
    (b) =>
      b.kind === 'hero' &&
      status(b).tone === 'ok' &&
      !((b.audience ?? {}) as { scope?: string }).scope?.match(/guest|customer/),
  ),
);

function status(block: HomepageBlock): { label: string; tone: StatusTone; icon: string } {
  if (!block.is_published) {
    return { label: t('homepage.st_draft'), tone: 'neutral', icon: 'ph:pencil-simple-line' };
  }
  const now = Date.now();
  if (block.starts_at && new Date(block.starts_at).getTime() > now) {
    return { label: t('homepage.st_scheduled'), tone: 'warn', icon: 'ph:clock' };
  }
  if (block.ends_at && new Date(block.ends_at).getTime() <= now) {
    return { label: t('homepage.st_expired'), tone: 'neutral', icon: 'ph:calendar-x' };
  }
  return { label: t('homepage.st_live'), tone: 'ok', icon: 'ph:check-circle' };
}

function windowLabel(block: HomepageBlock): string {
  const from = block.starts_at
    ? t('homepage.from_date', { date: formatDateTime(block.starts_at) })
    : '';
  const to = block.ends_at ? t('homepage.until_date', { date: formatDateTime(block.ends_at) }) : '';
  return [from, to].filter(Boolean).join(' ');
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [list, groups] = await Promise.all([
      listHomepageBlocks(),
      listPriceGroups().catch(() => [] as PriceGroup[]),
    ]);
    blocks.value = list;
    priceGroups.value = groups;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// --- Formulaire ------------------------------------------------------------
const dialog = ref(false);
const pickerOpen = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editingId = ref<string | null>(null);
const pickedPreview = ref<string | null>(null);

interface BlockForm {
  kind: Kind;
  title: string;
  subtitle: string;
  cta_label: string;
  cta_link: string;
  media_id: string | null;
  image_url: string;
  alt: string;
  position: number;
  is_published: boolean;
  starts_at: string | null;
  ends_at: string | null;
  /** Translated texts per language (R9 / T3). */
  translations: Translations;
  /** Shop sections: how many items, over how many days (most viewed). */
  limit: number;
  days: number;
  /** Who sees it (R8). */
  scope: Scope;
  price_group_ids: string[];
  locales: string[];
}

const form = reactive<BlockForm>(emptyForm('banner'));
const content = useContentTranslations({
  form,
  fields: ['title', 'subtitle', 'cta_label', 'alt'],
  status: () => blocks.value.find((b) => b.id === editingId.value)?.translation_status,
});
const texts = content.texts;
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const snapshot = useFormSnapshot(() => form);
const guard = useDialogGuard({
  isOpen: () => dialog.value,
  close: () => (dialog.value = false),
  isDirty: snapshot.isDirty,
});

function emptyForm(kind: Kind): BlockForm {
  return {
    kind,
    title: '',
    subtitle: '',
    cta_label: '',
    cta_link: '',
    media_id: null,
    image_url: '',
    alt: '',
    position: 0,
    is_published: false,
    starts_at: null,
    ends_at: null,
    translations: {},
    limit: 8,
    days: 30,
    scope: 'all',
    price_group_ids: [],
    locales: [],
  };
}

const isBuiltin = computed(() => BUILTIN.includes(form.kind));

const previewSrc = computed(() => {
  if (pickedPreview.value) return pickedPreview.value;
  if (form.media_id) {
    return blocks.value.find((b) => b.media_id === form.media_id)?.image?.src ?? null;
  }
  return form.image_url.trim() || null;
});

function openCreate(kind: Kind = 'banner') {
  editingId.value = null;
  Object.assign(form, emptyForm(kind));
  // A shop section is shown as soon as it is added; a hero or a banner is
  // prepared as a draft first.
  form.is_published = BUILTIN.includes(kind);
  pickedPreview.value = null;
  dialogError.value = null;
  content.reset();
  snapshot.take();
  dialog.value = true;
}

function openEdit(block: HomepageBlock) {
  editingId.value = block.id;
  Object.assign(form, {
    kind: block.kind as Kind,
    title: block.title,
    subtitle: block.subtitle ?? '',
    cta_label: block.cta_label ?? '',
    cta_link: block.cta_link ?? '',
    media_id: block.media_id ?? null,
    image_url: block.media_id ? '' : (block.image_url ?? ''),
    alt: block.alt ?? '',
    position: block.position ?? 0,
    is_published: block.is_published ?? false,
    starts_at: toShopDateTimeInput(block.starts_at),
    ends_at: toShopDateTimeInput(block.ends_at),
    translations: cloneTranslations(block.translations),
    limit: Number((block.config as Record<string, number> | undefined)?.['limit'] ?? 8),
    days: Number((block.config as Record<string, number> | undefined)?.['days'] ?? 30),
    scope: (block.audience as { scope?: Scope } | undefined)?.scope ?? 'all',
    price_group_ids: [
      ...((block.audience as { price_group_ids?: string[] } | undefined)?.price_group_ids ?? []),
    ],
    locales: [...((block.audience as { locales?: string[] } | undefined)?.locales ?? [])],
  });
  content.reset();
  snapshot.take();
  pickedPreview.value = null;
  dialogError.value = null;
  dialog.value = true;
}

function onPick(asset: MediaAsset) {
  form.media_id = asset.id;
  form.image_url = '';
  pickedPreview.value = asset.variants?.[0]?.url ?? asset.url;
  if (!form.alt && asset.alt) form.alt = asset.alt;
}

function clearImage() {
  form.media_id = null;
  form.image_url = '';
  pickedPreview.value = null;
}

function configFromForm(): Record<string, number> {
  if (form.kind === 'popular') return { limit: form.limit, days: form.days };
  if (BUILTIN.includes(form.kind)) return { limit: form.limit };
  return {};
}

function payloadFromForm(): HomepageBlockWrite {
  const builtin = BUILTIN.includes(form.kind);
  return {
    kind: form.kind,
    title: form.title.trim(),
    subtitle: form.subtitle.trim() || null,
    cta_label: form.cta_label.trim() || null,
    cta_link: form.cta_link.trim() || null,
    media_id: form.media_id,
    image_url: form.media_id ? null : form.image_url.trim() || null,
    alt: form.alt.trim() || null,
    position: form.position,
    is_published: form.is_published,
    starts_at: fromShopDateTimeInput(form.starts_at),
    ends_at: fromShopDateTimeInput(form.ends_at),
    translations: form.translations,
    config: configFromForm(),
    audience: {
      scope: form.scope,
      price_group_ids: form.scope === 'customer' ? form.price_group_ids : [],
      locales: form.locales,
    },
    ...(builtin
      ? { cta_label: null, cta_link: null, media_id: null, image_url: null, alt: null }
      : {}),
  };
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    const payload = payloadFromForm();
    if (editingId.value) await saveHomepageBlock(editingId.value, payload);
    else await createHomepageBlock(payload);
    dialog.value = false;
    notice.value = t('homepage.saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

/** Moves a section one step up or down: the whole order is saved at once. */
async function move(index: number, delta: number) {
  const reordered = [...blocks.value];
  const [item] = reordered.splice(index, 1);
  if (!item) return;
  reordered.splice(index + delta, 0, item);
  error.value = null;
  reordering.value = true;
  try {
    blocks.value = await reorderHomepageBlocks(reordered.map((b) => b.id));
  } catch (err) {
    error.value = extractApiError(err) ?? t('homepage.reorder_failed');
    await load();
  } finally {
    reordering.value = false;
  }
}

async function remove(block: HomepageBlock) {
  if (!(await confirmDelete(block.title || defaultTitle(block.kind)))) return;
  error.value = null;
  try {
    await deleteHomepageBlock(block.id);
    notice.value = t('homepage.deleted', { title: block.title || defaultTitle(block.kind) });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.homepage-thumb {
  width: 96px;
  height: 64px;
  object-fit: cover;
  border-radius: 6px;
  background: var(--n-tile);

  &--empty {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

.homepage-preview {
  width: 240px;
  height: 160px;
  object-fit: cover;
  border-radius: var(--n-radius);
  background: var(--n-tile);
}
</style>
