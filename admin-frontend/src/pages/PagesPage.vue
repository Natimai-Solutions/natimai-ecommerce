<template>
  <q-page class="admin-page">
    <PageHeader title="Pages du site">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          label="Nouvelle page"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <p class="admin-hint">
      « comment-ca-marche » explique le principe des départs groupés (lien dans le bandeau et le
      pied de page). Une page « cgv » publiée remplace le texte par défaut des CGV ; supprimez-la
      pour y revenir. Une page en brouillon n'est pas visible sur le site.
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
            :label="props.row.is_published ? 'Publiée' : 'Brouillon'"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>Modifier</q-tooltip>
          </q-btn>
          <q-btn flat round dense icon="ph:trash" color="negative" @click="remove(props.row)">
            <q-tooltip>Supprimer (une page légale revient à son texte par défaut)</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">Aucune page.</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog" maximized>
      <q-card>
        <q-card-section class="app-dialog__head row items-center no-wrap q-gutter-x-sm">
          <h2 class="app-dialog__title col">
            {{ editing ? `Modifier « ${form.slug} »` : 'Nouvelle page' }}
          </h2>
          <q-btn flat round dense icon="ph:x" v-close-popup>
            <q-tooltip>Fermer</q-tooltip>
          </q-btn>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.slug"
                class="col-12 col-sm-4"
                label="Adresse (slug) *"
                hint="minuscules, chiffres, tirets — ex. comment-ca-marche, cgv"
                outlined
                dense
                :readonly="editing"
                :rules="[(v: string) => /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v) || 'Slug invalide']"
              />
              <q-input
                v-model="form.title"
                class="col-12 col-sm-6"
                label="Titre *"
                outlined
                dense
                :rules="[(v: string) => !!v.trim() || 'Titre requis']"
              />
              <q-toggle v-model="form.is_published" class="col-12 col-sm-2" label="Publiée" />
            </div>
            <q-editor
              ref="editorRef"
              v-model="form.body_html"
              min-height="50vh"
              :toolbar="toolbar"
              :definitions="editorDefinitions"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              label="Enregistrer"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
    <MediaPicker v-model="mediaPickerOpen" kind="page" @select="insertImage" />
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import type { QEditor, QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { formatDateTime } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import type { MediaAsset } from '@/api/media';
import { deletePage, listPages, savePage, type ContentPage } from '@/api/pages';
import { extractApiError } from '@/api/errors';

const pages = ref<ContentPage[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const columns: QTableColumn[] = [
  { name: 'slug', label: 'Adresse', field: 'slug', align: 'left' },
  { name: 'title', label: 'Titre', field: 'title', align: 'left' },
  { name: 'published', label: 'État', field: 'is_published', align: 'left' },
  {
    name: 'modified',
    label: 'Modifiée',
    field: 'modify_at',
    align: 'left',
    format: (v: string | null) => formatDateTime(v),
  },
  { name: 'actions', label: '', field: 'slug', align: 'right' },
];

const toolbar = [
  ['bold', 'italic', 'underline'],
  [{ label: 'Titre', icon: 'title', list: 'no-icons', options: ['h2', 'h3', 'p'] }],
  ['unordered', 'ordered'],
  ['link', 'image', 'hr'],
  ['undo', 'redo'],
];

// --- Images dans l'éditeur (médiathèque) ---
const editorRef = ref<QEditor | null>(null);
const mediaPickerOpen = ref(false);
const editorDefinitions = {
  image: {
    tip: 'Insérer une image de la médiathèque',
    icon: 'image',
    label: 'Image',
    handler: () => {
      // La position du curseur est gardée pour y insérer l'image au retour.
      editorRef.value?.caret.savePosition();
      mediaPickerOpen.value = true;
    },
  },
};

function escapeAttribute(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function insertImage(asset: MediaAsset) {
  const html =
    `<img src="${escapeAttribute(asset.url)}" srcset="${escapeAttribute(asset.srcset)}" ` +
    `sizes="(max-width: 767px) 100vw, 720px" width="${asset.width}" height="${asset.height}" ` +
    `alt="${escapeAttribute(asset.alt ?? '')}" loading="lazy">`;
  const editor = editorRef.value;
  if (!editor) {
    form.body_html += html;
    return;
  }
  editor.focus();
  editor.caret.restorePosition();
  editor.runCmd('insertHTML', html);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    pages.value = await listPages();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// --- Create / edit ---
const dialog = ref(false);
const editing = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive({ slug: '', title: '', body_html: '', is_published: false });

function openCreate() {
  editing.value = false;
  Object.assign(form, { slug: '', title: '', body_html: '', is_published: false });
  dialogError.value = null;
  dialog.value = true;
}

function openEdit(p: ContentPage) {
  editing.value = true;
  Object.assign(form, {
    slug: p.slug,
    title: p.title,
    body_html: p.body_html,
    is_published: p.is_published,
  });
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
    });
    dialog.value = false;
    notice.value = 'Page enregistrée.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

async function remove(p: ContentPage) {
  error.value = null;
  try {
    await deletePage(p.slug);
    notice.value = `« ${p.slug} » supprimée.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
  }
}

onMounted(load);
</script>
