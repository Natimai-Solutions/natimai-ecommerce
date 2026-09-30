<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Pages du site</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
      <q-btn color="primary" icon="add" label="Nouvelle page" no-caps @click="openCreate" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      « comment-ca-marche » explique le principe des départs groupés (lien dans le bandeau et le
      pied de page). Une page « cgv » publiée remplace le texte par défaut des CGV ; supprimez-la
      pour y revenir. Une page en brouillon n'est pas visible sur le site.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>{{
      notice
    }}</q-banner>

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
      <template #body-cell-published="props">
        <q-td :props="props">
          <q-chip
            dense
            size="sm"
            :color="props.row.is_published ? 'green' : 'grey-6'"
            text-color="white"
            :label="props.row.is_published ? 'Publiée' : 'Brouillon'"
          />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)" />
          <q-btn flat dense icon="delete" color="grey-8" @click="remove(props.row)">
            <q-tooltip>Supprimer (une page légale revient à son texte par défaut)</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-grey-6 q-pa-md">Aucune page.</div>
      </template>
    </q-table>

    <q-dialog v-model="dialog" maximized>
      <q-card>
        <q-card-section class="row items-center">
          <div class="text-h6 col">
            {{ editing ? `Modifier « ${form.slug} »` : 'Nouvelle page' }}
          </div>
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
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
              v-model="form.body_html"
              min-height="50vh"
              :toolbar="toolbar"
              :definitions="{}"
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { formatDateTime } from '@app/utils';
import { deletePage, listPages, savePage, type ContentPage } from 'src/api/pages';
import { extractApiError } from 'src/api/errors';

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
  ['link', 'hr'],
  ['undo', 'redo'],
];

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
