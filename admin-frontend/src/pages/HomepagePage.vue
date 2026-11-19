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

    <div v-if="error || notice || liveHeroes.length > 1" class="admin-notices">
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
            <q-select
              v-model="form.kind"
              :options="kindOptions"
              emit-value
              map-options
              outlined
              dense
              :label="$t('homepage.kind')"
              :disable="!!editingId"
              data-testid="homepage-kind"
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
              :label="
                form.kind === 'announcement'
                  ? $t('homepage.announcement_text')
                  : titleOptional
                    ? $t('homepage.section_title')
                    : $t('homepage.block_title')
              "
              :hint="
                form.kind === 'announcement'
                  ? $t('homepage.announcement_hint')
                  : titleOptional && defaultTitle(form.kind)
                    ? $t('homepage.section_title_hint', { title: defaultTitle(form.kind) })
                    : undefined
              "
              outlined
              dense
              :maxlength="form.kind === 'announcement' ? 160 : 200"
              :rules="
                content.isSource.value && !titleOptional
                  ? [(v: string) => !!v.trim() || $t('homepage.title_rule')]
                  : []
              "
              data-testid="homepage-title"
            />
            <q-input
              v-if="hasSubtitle"
              v-model="texts.subtitle"
              :label="$t('homepage.text')"
              type="textarea"
              autogrow
              outlined
              dense
              maxlength="500"
            />
            <template v-if="form.kind === 'rich_text'">
              <q-editor
                v-model="texts.body_html"
                min-height="10rem"
                :toolbar="[
                  ['bold', 'italic', 'underline'],
                  ['unordered', 'ordered', 'link'],
                  [{ label: $t('homepage.heading'), list: 'no-icons', options: ['p', 'h2', 'h3'] }],
                  ['removeFormat'],
                ]"
                data-testid="homepage-body"
              />
              <q-option-group
                v-model="form.image_side"
                :options="[
                  { label: $t('homepage.image_right'), value: 'right' },
                  { label: $t('homepage.image_left'), value: 'left' },
                ]"
                inline
              />
            </template>
            <div v-if="form.kind === 'reassurance'" class="homepage-items">
              <p class="admin-hint q-mb-sm">{{ $t('homepage.reassurance_hint') }}</p>
              <div
                v-for="(entry, index) in form.reassurance"
                :key="index"
                class="homepage-reassurance"
                data-testid="homepage-reassurance-item"
              >
                <div class="row q-col-gutter-sm items-start">
                  <q-select
                    v-model="entry.icon"
                    class="col-12 col-sm-3"
                    :options="iconOptions"
                    emit-value
                    map-options
                    outlined
                    dense
                    :label="$t('homepage.icon')"
                  >
                    <template #option="scope">
                      <q-item v-bind="scope.itemProps">
                        <q-item-section avatar><q-icon :name="scope.opt.icon" /></q-item-section>
                        <q-item-section>{{ scope.opt.label }}</q-item-section>
                      </q-item>
                    </template>
                  </q-select>
                  <q-input
                    v-model="entry.text"
                    class="col-12 col-sm-5"
                    outlined
                    dense
                    maxlength="80"
                    :label="$t('homepage.reassurance_text')"
                  />
                  <q-input
                    v-model="entry.link"
                    class="col-10 col-sm-3"
                    outlined
                    dense
                    maxlength="500"
                    :label="$t('homepage.link')"
                  />
                  <div class="col-2 col-sm-1">
                    <q-btn
                      flat
                      round
                      dense
                      icon="ph:x"
                      :aria-label="$t('common.delete')"
                      :disable="form.reassurance.length <= 2"
                      @click="form.reassurance.splice(index, 1)"
                    />
                  </div>
                  <q-input
                    v-for="lang in otherLocales"
                    :key="lang"
                    v-model="entry.translations[lang]"
                    class="col-12 col-sm-5 offset-sm-3"
                    outlined
                    dense
                    maxlength="80"
                    :label="`${$t('homepage.reassurance_text')} (${lang.toUpperCase()})`"
                  />
                </div>
              </div>
              <q-btn
                v-if="form.reassurance.length < 4"
                flat
                no-caps
                icon="ph:plus"
                :label="$t('homepage.reassurance_add')"
                @click="form.reassurance.push(emptyReassurance())"
              />
            </div>
            <div v-if="form.kind === 'collection'" class="row q-col-gutter-sm">
              <q-select
                v-model="form.source"
                class="col-12 col-sm-6"
                :options="sourceOptions"
                emit-value
                map-options
                outlined
                dense
                :label="$t('homepage.source')"
                data-testid="homepage-source"
              />
              <q-select
                v-if="form.source === 'category'"
                v-model="form.category_id"
                class="col-12 col-sm-6"
                :options="categoryOptions"
                emit-value
                map-options
                outlined
                dense
                :label="$t('homepage.category')"
              />
              <q-select
                v-if="['category', 'newest', 'promotion'].includes(form.source)"
                v-model="form.sort"
                class="col-12 col-sm-6"
                :options="sortOptions"
                emit-value
                map-options
                outlined
                dense
                :label="$t('homepage.sort')"
              />
            </div>
            <q-option-group
              v-if="form.kind === 'categories' || form.kind === 'brand_strip'"
              v-model="form.mode"
              :options="[
                { label: $t('homepage.mode_auto'), value: 'auto' },
                { label: $t('homepage.mode_manual'), value: 'manual' },
              ]"
              inline
            />
            <div v-if="listsItems" class="homepage-items">
              <q-select
                v-if="form.kind === 'collection'"
                :model-value="null"
                :options="productChoices"
                use-input
                input-debounce="300"
                outlined
                dense
                :label="$t('homepage.add_product')"
                data-testid="homepage-add-product"
                @filter="onProductFilter"
                @update:model-value="addItem"
              >
                <template #no-option>
                  <q-item
                    ><q-item-section class="text-subtle">{{
                      productTerm.length < 2
                        ? $t('homepage.search_hint')
                        : $t('homepage.no_product')
                    }}</q-item-section></q-item
                  >
                </template>
              </q-select>
              <q-select
                v-else-if="form.kind === 'brand_strip'"
                :model-value="null"
                :options="brandOptions.filter((o) => !form.items.some((i) => i.id === o.value))"
                outlined
                dense
                :label="$t('homepage.add_brand')"
                :hint="$t('homepage.add_brand_hint')"
                data-testid="homepage-add-brand"
                @update:model-value="addItem"
              />
              <q-select
                v-else
                :model-value="null"
                :options="categoryOptions.filter((o) => !form.items.some((i) => i.id === o.value))"
                emit-value
                map-options
                outlined
                dense
                :label="$t('homepage.add_category')"
                @update:model-value="
                  (id: string) => addItem({ value: id, label: categoryName(id) })
                "
              />
              <q-list v-if="form.items.length" bordered separator dense class="q-mt-sm">
                <q-item v-for="(entry, index) in form.items" :key="entry.id">
                  <q-item-section>{{ entry.name }}</q-item-section>
                  <q-item-section v-if="form.kind === 'categories'" side>
                    <q-input
                      v-model="entry.label"
                      dense
                      outlined
                      maxlength="100"
                      :placeholder="$t('homepage.item_label')"
                    />
                  </q-item-section>
                  <q-item-section side>
                    <div class="row no-wrap">
                      <q-btn
                        flat
                        round
                        dense
                        icon="ph:arrow-up"
                        :aria-label="$t('homepage.up')"
                        :disable="index === 0"
                        @click="moveItem(index, -1)"
                      />
                      <q-btn
                        flat
                        round
                        dense
                        icon="ph:arrow-down"
                        :aria-label="$t('homepage.down')"
                        :disable="index === form.items.length - 1"
                        @click="moveItem(index, 1)"
                      />
                      <q-btn
                        flat
                        round
                        dense
                        icon="ph:x"
                        :aria-label="$t('common.delete')"
                        @click="form.items.splice(index, 1)"
                      />
                    </div>
                  </q-item-section>
                </q-item>
              </q-list>
              <p v-else class="admin-hint q-mt-sm">{{ $t('homepage.items_empty') }}</p>
            </div>
            <div v-if="isBuiltin || form.kind === 'brand_strip'" class="row q-col-gutter-sm">
              <q-input
                v-model.number="form.limit"
                class="col-12 col-sm-4"
                type="number"
                :min="form.kind === 'brand_strip' ? 3 : 2"
                :max="24"
                :label="
                  form.kind === 'categories'
                    ? $t('homepage.limit_categories')
                    : form.kind === 'brand_strip'
                      ? $t('homepage.limit_brands')
                      : $t('homepage.limit_products')
                "
                outlined
                dense
                data-testid="homepage-limit"
              />
              <q-input
                v-if="
                  form.kind === 'popular' ||
                  (form.kind === 'collection' && ['popular', 'best_sellers'].includes(form.source))
                "
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
            <div v-if="hasCta" class="row q-col-gutter-sm">
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

            <template v-if="hasImage">
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
              v-if="form.kind !== 'announcement'"
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
import { listCategories, type Category } from '@/api/categories';
import { searchProducts } from '@/api/discounts';
import { useShopConfigStore } from '@/stores/shopConfig';
import type { MediaAsset } from '@/api/media';
import { listBrands, type AdminBrand } from '@/api/brands';

const { t } = useI18n();
const { confirmDelete } = useConfirm();

type Kind =
  | 'hero'
  | 'banner'
  | 'announcement'
  | 'reassurance'
  | 'brand_strip'
  | 'rich_text'
  | 'categories'
  | 'featured'
  | 'popular'
  | 'collection';
type Scope = 'all' | 'guest' | 'customer';
type Source = 'manual' | 'category' | 'newest' | 'promotion' | 'popular' | 'best_sellers';
const BUILTIN: Kind[] = ['categories', 'featured', 'popular', 'collection'];
/** Lot A3: written in the admin, the title optional. */
const TITLE_OPTIONAL: Kind[] = [...BUILTIN, 'reassurance', 'brand_strip', 'rich_text'];
/** The closed list of pictograms of a reassurance band (as the API). */
const REASSURANCE_ICONS: Record<string, string> = {
  truck: 'ph:truck',
  boat: 'ph:boat',
  map_pin: 'ph:map-pin',
  package: 'ph:package',
  lock: 'ph:lock-simple',
  shield: 'ph:shield-check',
  credit_card: 'ph:credit-card',
  seal: 'ph:seal-check',
  chat: 'ph:chat-circle-text',
  phone: 'ph:phone',
  clock: 'ph:clock',
  returns: 'ph:arrow-counter-clockwise',
  tag: 'ph:tag',
  star: 'ph:star',
};
interface ReassuranceEntry {
  icon: string;
  text: string;
  link: string;
  translations: Record<string, string>;
}
/** A key of the closed list (not an icon name: the storefront draws it). */
const FIRST_PICTOGRAM = Object.keys(REASSURANCE_ICONS)[0] ?? '';
function emptyReassurance(): ReassuranceEntry {
  return { icon: FIRST_PICTOGRAM, text: '', link: '', translations: {} };
}
interface ListedItem {
  id: string;
  name: string;
  label: string;
}

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
  { label: t('homepage.kind_announcement'), value: 'announcement' },
  { label: t('homepage.kind_reassurance'), value: 'reassurance' },
  { label: t('homepage.kind_brand_strip'), value: 'brand_strip' },
  { label: t('homepage.kind_rich_text'), value: 'rich_text' },
  { label: t('homepage.kind_categories'), value: 'categories' },
  { label: t('homepage.kind_featured'), value: 'featured' },
  { label: t('homepage.kind_popular'), value: 'popular' },
  { label: t('homepage.kind_collection'), value: 'collection' },
]);

const sourceOptions = computed(() =>
  (['manual', 'category', 'newest', 'promotion', 'popular', 'best_sellers'] as Source[]).map(
    (value) => ({ value, label: t(`homepage.source_${value}`) }),
  ),
);
const sortOptions = computed(() =>
  ['newest', 'price_asc', 'price_desc', 'name'].map((value) => ({
    value,
    label: t(`homepage.sort_${value}`),
  })),
);
const categories = ref<Category[]>([]);
const categoryOptions = computed(() =>
  categories.value
    .map((c) => ({ value: c.id, label: c.name }))
    .sort((a, b) => a.label.localeCompare(b.label, 'fr')),
);
function categoryName(id: string): string {
  return categories.value.find((c) => c.id === id)?.name ?? id;
}
const productChoices = ref<{ value: string; label: string }[]>([]);
const productTerm = ref('');
function onProductFilter(term: string, update: (fn: () => void) => void) {
  productTerm.value = term.trim();
  if (term.trim().length < 2) {
    update(() => (productChoices.value = []));
    return;
  }
  void searchProducts(term.trim()).then((found) =>
    update(() => {
      productChoices.value = found
        .filter((p) => !form.items.some((i) => i.id === p.id))
        .map((p) => ({
          value: p.id,
          label: p.supplier_sku ? `${p.name} · ${p.supplier_sku}` : p.name,
        }));
    }),
  );
}
function addItem(choice: { value: string; label: string } | null) {
  if (!choice || form.items.some((i) => i.id === choice.value)) return;
  form.items.push({ id: choice.value, name: choice.label, label: '' });
}
function moveItem(index: number, delta: number) {
  const [entry] = form.items.splice(index, 1);
  if (entry) form.items.splice(index + delta, 0, entry);
}

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
      collection: 'ph:stack',
      announcement: 'ph:megaphone',
      reassurance: 'ph:seal-check',
      brand_strip: 'ph:tag',
      rich_text: 'ph:text-align-left',
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
      collection: t('homepage.default_collection'),
      brand_strip: t('homepage.default_brands'),
    }[kind] ?? ''
  );
}

function configLabel(block: HomepageBlock): string {
  const config = (block.config ?? {}) as Record<string, number>;
  if (block.kind === 'popular') {
    return t('homepage.config_popular', { n: config['limit'] ?? 8, days: config['days'] ?? 30 });
  }
  if (block.kind === 'collection') {
    const source = (block.config as { source?: string } | undefined)?.source ?? 'manual';
    return `${t(`homepage.source_${source}`)} · ${t('homepage.config_limit', { n: config['limit'] ?? 8 })}`;
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
    const [list, groups, cats, brandList] = await Promise.all([
      listHomepageBlocks(),
      listPriceGroups().catch(() => [] as PriceGroup[]),
      listCategories().catch(() => [] as Category[]),
      listBrands({}).catch(() => null),
    ]);
    brands.value = brandList?.data ?? [];
    blocks.value = list;
    priceGroups.value = groups;
    categories.value = cats;
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
  /** Selection (lot A2). */
  source: Source;
  category_id: string | null;
  sort: string;
  mode: 'auto' | 'manual';
  items: ListedItem[];
  /** Lot A3: free text, its image side; pictograms of a reassurance band. */
  body_html: string;
  image_side: 'left' | 'right';
  reassurance: ReassuranceEntry[];
  /** Who sees it (R8). */
  scope: Scope;
  price_group_ids: string[];
  locales: string[];
}

const form = reactive<BlockForm>(emptyForm('banner'));
const content = useContentTranslations({
  form,
  fields: ['title', 'subtitle', 'cta_label', 'alt', 'body_html'],
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
    source: 'manual',
    category_id: null,
    sort: 'newest',
    mode: 'auto',
    items: [],
    body_html: '',
    image_side: 'right',
    reassurance: kind === 'reassurance' ? [emptyReassurance(), emptyReassurance()] : [],
    scope: 'all',
    price_group_ids: [],
    locales: [],
  };
}

const isBuiltin = computed(() => BUILTIN.includes(form.kind));
const titleOptional = computed(() => TITLE_OPTIONAL.includes(form.kind));
const hasCta = computed(() => ['hero', 'banner', 'announcement'].includes(form.kind));
const hasImage = computed(() => ['hero', 'banner', 'rich_text'].includes(form.kind));
const hasSubtitle = computed(
  () => !['announcement', 'reassurance', 'rich_text'].includes(form.kind),
);
const otherLocales = computed(() => (shop.config?.available_locales ?? ['fr', 'en']).slice(1));
const iconOptions = computed(() =>
  Object.entries(REASSURANCE_ICONS).map(([value, icon]) => ({
    value,
    icon,
    label: t(`homepage.icon_${value}`),
  })),
);
const brands = ref<AdminBrand[]>([]);
const brandOptions = computed(() =>
  brands.value
    .filter((b) => b.is_active)
    .map((b) => ({
      value: b.id,
      label: b.is_validated ? b.name : `${b.name} (${t('brands.to_validate')})`,
    })),
);
/** The section lists products (manual selection) or categories (manual mode). */
const listsItems = computed(
  () =>
    (form.kind === 'collection' && form.source === 'manual') ||
    (form.kind === 'categories' && form.mode === 'manual') ||
    (form.kind === 'brand_strip' && form.mode === 'manual'),
);

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
  if (kind === 'brand_strip') form.limit = 12;
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
    source: (block.config as { source?: Source } | undefined)?.source ?? 'manual',
    category_id: (block.config as { category_id?: string } | undefined)?.category_id ?? null,
    sort: (block.config as { sort?: string } | undefined)?.sort ?? 'newest',
    mode: ((block.config as { mode?: string } | undefined)?.mode ?? 'auto') as 'auto' | 'manual',
    body_html: block.body_html ?? '',
    image_side: ((block.config as { image_side?: string } | undefined)?.image_side ??
      'right') as 'left' | 'right',
    reassurance: (
      (block.config as { items?: Partial<ReassuranceEntry>[] } | undefined)?.items ?? []
    ).map((entry) => ({
      icon: entry.icon ?? FIRST_PICTOGRAM,
      text: entry.text ?? '',
      link: entry.link ?? '',
      translations: { ...(entry.translations ?? {}) },
    })),
    items: (block.items ?? []).map((item) => ({
      id: (item.product_id ?? item.category_id ?? item.brand_id) as string,
      name: item.name,
      label: item.label ?? '',
    })),
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

function configFromForm(): Record<string, unknown> {
  if (form.kind === 'popular') return { limit: form.limit, days: form.days };
  if (form.kind === 'categories') return { limit: form.limit, mode: form.mode };
  if (form.kind === 'collection') {
    return {
      source: form.source,
      limit: form.limit,
      ...(form.source === 'category' ? { category_id: form.category_id } : {}),
      ...(['popular', 'best_sellers'].includes(form.source) ? { days: form.days } : {}),
      ...(['category', 'newest', 'promotion'].includes(form.source) ? { sort: form.sort } : {}),
    };
  }
  if (BUILTIN.includes(form.kind)) return { limit: form.limit };
  if (form.kind === 'brand_strip') return { mode: form.mode, limit: form.limit };
  if (form.kind === 'rich_text') return { image_side: form.image_side };
  if (form.kind === 'reassurance') {
    return {
      items: form.reassurance.map((entry) => ({
        icon: entry.icon,
        text: entry.text.trim(),
        link: entry.link.trim() || null,
        translations: Object.fromEntries(
          Object.entries(entry.translations).filter(([, text]) => text?.trim()),
        ),
      })),
    };
  }
  return {};
}

function itemsFromForm(): {
  product_id?: string;
  category_id?: string;
  brand_id?: string;
  label?: string | null;
}[] {
  if (!listsItems.value) return [];
  return form.items.map((item) =>
    form.kind === 'collection'
      ? { product_id: item.id }
      : form.kind === 'brand_strip'
        ? { brand_id: item.id }
        : { category_id: item.id, label: item.label.trim() || null },
  );
}

function payloadFromForm(): HomepageBlockWrite {
  return {
    kind: form.kind,
    title: form.title.trim(),
    subtitle: form.subtitle.trim() || null,
    cta_label: form.cta_label.trim() || null,
    cta_link: form.cta_link.trim() || null,
    media_id: form.media_id,
    image_url: form.media_id ? null : form.image_url.trim() || null,
    alt: form.alt.trim() || null,
    body_html: form.kind === 'rich_text' ? form.body_html : null,
    position: form.position,
    is_published: form.is_published,
    starts_at: fromShopDateTimeInput(form.starts_at),
    ends_at: fromShopDateTimeInput(form.ends_at),
    translations: form.translations,
    config: configFromForm(),
    items: itemsFromForm(),
    audience: {
      scope: form.kind === 'announcement' ? 'all' : form.scope,
      price_group_ids:
        form.scope === 'customer' && form.kind !== 'announcement' ? form.price_group_ids : [],
      locales: form.locales,
    },
    ...(hasCta.value ? {} : { cta_label: null, cta_link: null }),
    ...(hasImage.value ? {} : { media_id: null, image_url: null, alt: null }),
    ...(hasSubtitle.value ? {} : { subtitle: null }),
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
.homepage-reassurance {
  padding: 12px 0;
  border-bottom: 1px solid var(--n-line);
}

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

.homepage-items {
  margin-top: 4px;
}

.homepage-preview {
  width: 240px;
  height: 160px;
  object-fit: cover;
  border-radius: var(--n-radius);
  background: var(--n-tile);
}
</style>
