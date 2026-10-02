<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('pages.title')">
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
          outline
          no-caps
          color="primary"
          icon="ph:file-text"
          :label="$t('pages.from_template')"
          :loading="templateLoading"
          data-testid="pages-from-template"
        >
          <q-list>
            <q-item
              v-for="tpl in templates"
              :key="tpl.slug"
              clickable
              v-close-popup
              @click="openFromTemplate(tpl)"
            >
              <q-item-section>
                <q-item-label>{{ tpl.title }}</q-item-label>
                <q-item-label caption>
                  <span class="font-mono">{{ tpl.slug }}</span>
                  <template v-if="tpl.page_exists"> · {{ $t('pages.template_exists') }}</template>
                </q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="templates.length === 0">
              <q-item-section class="text-subtle">{{ $t('pages.no_template') }}</q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('pages.new')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <p class="admin-hint">
      {{ $t('pages.intro') }}
    </p>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <q-table
      :rows="pages"
      :columns="columns"
      row-key="slug"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-slug="props">
        <q-td :props="props" class="font-mono">{{ props.row.slug }}</q-td>
      </template>
      <template #body-cell-published="props">
        <q-td :props="props">
          <StatusTag
            :tone="props.row.is_published ? 'ok' : 'neutral'"
            :icon="props.row.is_published ? 'ph:check-circle' : 'ph:pencil-simple-line'"
            :label="props.row.is_published ? $t('pages.st_published') : $t('pages.st_draft')"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense icon="ph:trash" color="negative" @click="remove(props.row)">
            <q-tooltip>{{ $t('pages.delete') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('pages.none') }}</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog" maximized>
      <q-card>
        <q-card-section class="app-dialog__head row items-center no-wrap q-gutter-x-sm">
          <h2 class="app-dialog__title col">
            {{ editing ? $t('pages.edit_title', { slug: form.slug }) : $t('pages.new_title') }}
          </h2>
          <q-btn flat round dense icon="ph:x" v-close-popup>
            <q-tooltip>{{ $t('common.close') }}</q-tooltip>
          </q-btn>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <AppNotice v-if="fromTemplate" tone="info" dense data-testid="pages-template-notice">
              {{
                editing
                  ? $t('pages.template_replaces', { slug: form.slug })
                  : $t('pages.template_hint')
              }}
            </AppNotice>
            <ContentLanguageTabs
              v-model="content.lang.value"
              :source="content.source.value"
              :locales="content.locales.value"
              :status-of="content.statusOf"
              :reviewed="content.reviewed.value"
              @review="content.markReviewed"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.slug"
                class="col-12 col-sm-4"
                :label="$t('pages.slug')"
                :hint="$t('pages.slug_hint')"
                outlined
                dense
                :readonly="editing || fromTemplate"
                :rules="[
                  (v: string) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v) || $t('pages.slug_rule'),
                ]"
              />
              <q-input
                v-model="texts.title"
                class="col-12 col-sm-6"
                :label="$t('pages.page_title')"
                outlined
                dense
                :rules="
                  content.isSource.value
                    ? [(v: string) => !!v.trim() || $t('pages.title_rule')]
                    : []
                "
              />
              <q-toggle
                v-model="form.is_published"
                class="col-12 col-sm-2"
                :label="$t('pages.published')"
              />
            </div>
            <RichTextEditor v-model="texts.body_html" min-height="50vh" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { formatDateTime } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import RichTextEditor from '@/components/RichTextEditor.vue';
import ContentLanguageTabs from '@/components/ContentLanguageTabs.vue';
import {
  cloneTranslations,
  useContentTranslations,
  type Translations,
} from '@/composables/useContentTranslations';
import {
  deletePage,
  getPageTemplate,
  listPages,
  listPageTemplates,
  savePage,
  type ContentPage,
  type ContentPageTemplateSummary,
} from '@/api/pages';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const pages = ref<ContentPage[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const columns = computed<QTableColumn[]>(() => [
  { name: 'slug', label: t('pages.col_slug'), field: 'slug', align: 'left' },
  { name: 'title', label: t('pages.col_title'), field: 'title', align: 'left' },
  { name: 'published', label: t('pages.col_state'), field: 'is_published', align: 'left' },
  {
    name: 'modified',
    label: t('pages.col_modified'),
    field: 'modify_at',
    align: 'left',
    format: (v: string | null) => formatDateTime(v),
  },
  { name: 'actions', label: '', field: 'slug', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [pages.value, templates.value] = await Promise.all([listPages(), listPageTemplates()]);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// --- Built-in legal templates (R9 / T1) ---
const templates = ref<ContentPageTemplateSummary[]>([]);
const templateLoading = ref(false);
/** The dialog was opened from a template (slug fixed, text pre-filled). */
const fromTemplate = ref(false);

async function openFromTemplate(tpl: ContentPageTemplateSummary) {
  templateLoading.value = true;
  error.value = null;
  try {
    const rendered = await getPageTemplate(tpl.slug);
    const existing = pages.value.find((p) => p.slug === tpl.slug);
    editing.value = existing !== undefined;
    Object.assign(form, {
      slug: tpl.slug,
      title: existing?.title ?? rendered.title,
      body_html: rendered.body_html,
      is_published: existing?.is_published ?? false,
      translations: cloneTranslations(existing?.translations),
    });
    content.reset();
    fromTemplate.value = true;
    dialogError.value = null;
    dialog.value = true;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    templateLoading.value = false;
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editing = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive<{
  slug: string;
  title: string;
  body_html: string;
  is_published: boolean;
  translations: Translations;
}>({ slug: '', title: '', body_html: '', is_published: false, translations: {} });
const content = useContentTranslations({
  form,
  fields: ['title', 'body_html'],
  status: () => pages.value.find((p) => p.slug === form.slug)?.translation_status,
});
const texts = content.texts;

function openCreate() {
  editing.value = false;
  fromTemplate.value = false;
  Object.assign(form, {
    slug: '',
    title: '',
    body_html: '',
    is_published: false,
    translations: {},
  });
  content.reset();
  dialogError.value = null;
  dialog.value = true;
}

function openEdit(p: ContentPage) {
  editing.value = true;
  fromTemplate.value = false;
  Object.assign(form, {
    slug: p.slug,
    title: p.title,
    body_html: p.body_html,
    is_published: p.is_published,
    translations: cloneTranslations(p.translations),
  });
  content.reset();
  dialogError.value = null;
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    await savePage(form.slug.trim(), {
      title: form.title.trim(),
      body_html: form.body_html,
      is_published: form.is_published,
      translations: form.translations,
    });
    dialog.value = false;
    notice.value = t('pages.saved');
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function remove(p: ContentPage) {
  error.value = null;
  try {
    await deletePage(p.slug);
    notice.value = t('pages.deleted', { slug: p.slug });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  }
}

onMounted(load);
</script>
