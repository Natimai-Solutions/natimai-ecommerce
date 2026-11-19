<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('brands.title')" :hint="$t('brands.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:link"
          :label="$t('brands.link_now')"
          :loading="linking"
          data-testid="brands-link"
          @click="linkNow"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('brands.new')"
          data-testid="brands-new"
          @click="openEdit(null)"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
    <AppNotice v-if="info" tone="success" class="q-mb-md">{{ info }}</AppNotice>

    <div class="row items-center q-gutter-sm q-mb-md">
      <q-input
        v-model="search"
        outlined
        dense
        clearable
        debounce="300"
        class="brands__search"
        :placeholder="$t('brands.search')"
        @update:model-value="load"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-toggle
        v-model="onlyToValidate"
        :label="$t('brands.only_to_validate', { n: toValidate })"
        @update:model-value="load"
      />
    </div>

    <div v-if="loading && !brands.length" class="q-pa-md">
      <q-skeleton v-for="n in 4" :key="n" type="text" class="q-mb-sm" />
    </div>
    <div v-else-if="!brands.length" class="app-empty">
      <q-icon name="ph:tag" size="28px" class="text-subtle" />
      <h3>{{ $t('brands.empty') }}</h3>
    </div>
    <q-list v-else bordered separator class="rounded-borders">
      <q-item v-for="brand in brands" :key="brand.id" data-testid="brand-row">
        <q-item-section avatar>
          <img v-if="brand.logo" :src="brand.logo.src" alt="" class="brands__logo" />
          <q-icon v-else name="ph:tag" size="24px" class="text-subtle" />
        </q-item-section>
        <q-item-section>
          <q-item-label class="text-weight-medium">
            {{ brand.name }}
            <q-badge
              v-if="!brand.is_validated"
              color="warning"
              text-color="dark"
              class="q-ml-sm"
              :label="$t('brands.to_validate')"
            />
            <q-badge
              v-else-if="!brand.is_active"
              outline
              color="primary"
              class="q-ml-sm"
              :label="$t('brands.hidden')"
            />
          </q-item-label>
          <q-item-label caption>
            /marque/{{ brand.slug }} ·
            {{ $t('brands.products', { n: brand.product_count }, brand.product_count) }}
            <template v-if="brand.aliases?.length">
              · {{ $t('brands.aliases_short') }} {{ brand.aliases.join(', ') }}
            </template>
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div class="row no-wrap">
            <q-btn
              v-if="!brand.is_validated"
              flat
              dense
              no-caps
              color="positive"
              icon="ph:check"
              :label="$t('brands.validate')"
              data-testid="brand-validate"
              @click="validate(brand)"
            />
            <q-btn
              flat
              round
              dense
              icon="ph:arrows-merge"
              :aria-label="$t('brands.merge')"
              @click="openMerge(brand)"
            >
              <q-tooltip>{{ $t('brands.merge') }}</q-tooltip>
            </q-btn>
            <q-btn
              flat
              round
              dense
              icon="ph:pencil-simple"
              :aria-label="$t('common.edit')"
              data-testid="brand-edit"
              @click="openEdit(brand)"
            />
            <q-btn
              flat
              round
              dense
              icon="ph:trash"
              color="negative"
              :aria-label="$t('common.delete')"
              @click="remove(brand)"
            />
          </div>
        </q-item-section>
      </q-item>
    </q-list>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editingId ? $t('brands.edit_title') : $t('brands.new') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.name"
              outlined
              dense
              maxlength="100"
              :label="$t('brands.name')"
              :rules="[(v: string) => !!v.trim() || $t('brands.required')]"
              data-testid="brand-name"
            />
            <q-input
              v-model="form.slug"
              outlined
              dense
              maxlength="120"
              prefix="/marque/"
              :label="$t('brands.slug')"
              :hint="$t('brands.slug_hint')"
            />
            <q-input
              v-model="form.description"
              type="textarea"
              autogrow
              outlined
              maxlength="500"
              counter
              :label="$t('brands.description')"
            />
            <q-input
              v-for="lang in otherLocales"
              :key="lang"
              v-model="form.translations[lang]"
              type="textarea"
              autogrow
              outlined
              maxlength="500"
              :label="`${$t('brands.description')} (${lang.toUpperCase()})`"
              :data-testid="`brand-description-${lang}`"
            />
            <div class="row items-center q-gutter-sm">
              <img v-if="formLogo" :src="formLogo" alt="" class="brands__logo brands__logo--lg" />
              <q-btn
                outline
                no-caps
                icon="ph:image"
                :label="$t('brands.choose_logo')"
                @click="pickerOpen = true"
              />
              <q-btn
                v-if="form.media_id"
                flat
                no-caps
                color="negative"
                :label="$t('brands.remove_logo')"
                @click="clearLogo"
              />
            </div>
            <q-select
              v-model="form.aliases"
              outlined
              dense
              multiple
              use-chips
              use-input
              hide-dropdown-icon
              new-value-mode="add-unique"
              input-debounce="0"
              :label="$t('brands.aliases')"
              :hint="$t('brands.aliases_hint')"
            />
            <q-toggle v-model="form.is_validated" :label="$t('brands.validated')" />
            <q-toggle v-model="form.is_active" :label="$t('brands.active')" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="dialog = false" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
              data-testid="brand-save"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <q-dialog v-model="mergeDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('brands.merge_title', { name: merging?.name }) }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <p class="text-subtle q-ma-none">{{ $t('brands.merge_hint') }}</p>
          <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
          <q-select
            v-model="mergeTarget"
            outlined
            dense
            emit-value
            map-options
            :options="mergeOptions"
            :label="$t('brands.merge_into')"
            data-testid="brand-merge-target"
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" @click="mergeDialog = false" />
          <q-btn
            color="primary"
            unelevated
            no-caps
            :disable="!mergeTarget"
            :loading="saving"
            :label="$t('brands.merge')"
            data-testid="brand-merge-save"
            @click="submitMerge"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <MediaPicker v-model="pickerOpen" kind="other" @select="onPick" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';

import MediaPicker from '@/components/MediaPicker.vue';
import PageHeader from '@/components/PageHeader.vue';
import { useConfirm } from '@/composables/useConfirm';
import { extractApiError } from '@/api/errors';
import {
  deleteBrand,
  linkBrands,
  listBrands,
  mergeBrand,
  saveBrand,
  type AdminBrand,
} from '@/api/brands';
import type { MediaAsset } from '@/api/media';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();
const shop = useShopConfigStore();
/** The languages offered besides the shop's own (the source text). */
const otherLocales = computed<string[]>(() =>
  (shop.config?.available_locales ?? ['fr', 'en']).slice(1),
);
const { confirmDelete } = useConfirm();

const brands = ref<AdminBrand[]>([]);
const toValidate = ref(0);
const loading = ref(false);
const linking = ref(false);
const error = ref<string | null>(null);
const info = ref<string | null>(null);
const search = ref<string | null>('');
const onlyToValidate = ref(false);

const dialog = ref(false);
const dialogError = ref<string | null>(null);
const saving = ref(false);
const editingId = ref<string | null>(null);
const pickerOpen = ref(false);
const formLogo = ref<string | null>(null);

interface BrandForm {
  /** The description in the other offered languages. */
  translations: Record<string, string>;
  name: string;
  slug: string;
  description: string;
  media_id: string | null;
  aliases: string[];
  is_validated: boolean;
  is_active: boolean;
}

const form = reactive<BrandForm>({
  translations: {},
  name: '',
  slug: '',
  description: '',
  media_id: null,
  aliases: [],
  is_validated: true,
  is_active: true,
});

const mergeDialog = ref(false);
const merging = ref<AdminBrand | null>(null);
const mergeTarget = ref<string | null>(null);
const mergeOptions = computed(() =>
  brands.value
    .filter((b) => b.id !== merging.value?.id)
    .map((b) => ({ label: b.name, value: b.id })),
);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const page = await listBrands({
      q: search.value?.trim() || null,
      to_validate: onlyToValidate.value,
    });
    brands.value = page.data;
    toValidate.value = page.to_validate;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function bodyOf(brand: AdminBrand) {
  return {
    name: brand.name,
    slug: brand.slug,
    description: brand.description ?? null,
    media_id: brand.media_id ?? null,
    aliases: brand.aliases ?? [],
    is_validated: brand.is_validated,
    is_active: brand.is_active,
    // Sent back as they are: an empty mapping would erase them.
    translations: brand.translations ?? {},
  };
}

function openEdit(brand: AdminBrand | null) {
  editingId.value = brand?.id ?? null;
  dialogError.value = null;
  form.name = brand?.name ?? '';
  form.slug = brand?.slug ?? '';
  form.description = brand?.description ?? '';
  form.media_id = brand?.media_id ?? null;
  form.aliases = [...(brand?.aliases ?? [])];
  form.is_validated = brand?.is_validated ?? true;
  form.is_active = brand?.is_active ?? true;
  form.translations = Object.fromEntries(
    otherLocales.value.map((lang) => {
      const texts = (brand?.translations ?? {})[lang] as Record<string, unknown> | undefined;
      return [lang, typeof texts?.['description'] === 'string' ? texts['description'] : ''];
    }),
  );
  formLogo.value = brand?.logo?.src ?? null;
  dialog.value = true;
}

function onPick(asset: MediaAsset) {
  form.media_id = asset.id;
  formLogo.value = asset.url;
  pickerOpen.value = false;
}

function clearLogo() {
  form.media_id = null;
  formLogo.value = null;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    await saveBrand(
      {
        name: form.name.trim(),
        slug: form.slug.trim() || null,
        description: form.description.trim() || null,
        media_id: form.media_id,
        aliases: form.aliases,
        is_validated: form.is_validated,
        is_active: form.is_active,
        translations: Object.fromEntries(
          Object.entries(form.translations)
            .filter(([, text]) => text.trim())
            .map(([lang, text]) => [lang, { description: text.trim() }]),
        ),
      },
      editingId.value ?? undefined,
    );
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function validate(brand: AdminBrand) {
  error.value = null;
  try {
    await saveBrand({ ...bodyOf(brand), is_validated: true }, brand.id);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  }
}

function openMerge(brand: AdminBrand) {
  merging.value = brand;
  mergeTarget.value = null;
  dialogError.value = null;
  mergeDialog.value = true;
}

async function submitMerge() {
  if (!merging.value || !mergeTarget.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await mergeBrand(merging.value.id, mergeTarget.value);
    mergeDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function remove(brand: AdminBrand) {
  if (!(await confirmDelete(brand.name, t('brands.delete_warning')))) return;
  try {
    await deleteBrand(brand.id);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  }
}

async function linkNow() {
  linking.value = true;
  error.value = null;
  info.value = null;
  try {
    const linked = await linkBrands();
    info.value = t('brands.linked', { n: linked }, linked);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    linking.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.brands__search {
  min-width: 260px;
}

.brands__logo {
  width: 40px;
  height: 40px;
  object-fit: contain;
  border-radius: 6px;
  background: var(--n-surface);
  border: 1px solid var(--n-line);
  padding: 2px;
}

.brands__logo--lg {
  width: 64px;
  height: 64px;
}
</style>
