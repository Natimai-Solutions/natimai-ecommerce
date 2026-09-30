<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Accueil du site</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
      <q-btn
        color="primary"
        icon="add"
        label="Nouveau bloc"
        no-caps
        data-testid="homepage-new"
        @click="openCreate()"
      />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Le <strong>hero</strong> est le grand bandeau en haut de l'accueil (le premier publié
      s'affiche, sinon un texte par défaut). Les <strong>bannières</strong> suivent, dans l'ordre
      indiqué. Un bloc programmé n'apparaît qu'entre ses dates de début et de fin.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>
      {{ notice }}
    </q-banner>

    <div v-if="loading && !blocks.length" class="row justify-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <template v-else>
      <div v-for="group in groups" :key="group.kind" class="q-mb-lg">
        <div class="text-subtitle1 text-weight-medium q-mb-sm">{{ group.label }}</div>
        <div v-if="!group.blocks.length" class="text-grey-7 q-pa-sm">
          Aucun {{ group.kind === 'hero' ? 'hero' : 'bannière' }}.
          <q-btn
            flat
            dense
            no-caps
            color="primary"
            :label="`Ajouter ${group.kind === 'hero' ? 'un hero' : 'une bannière'}`"
            @click="openCreate(group.kind)"
          />
        </div>
        <q-list v-else bordered separator class="rounded-borders">
          <q-item v-for="(block, index) in group.blocks" :key="block.id">
            <q-item-section avatar>
              <img
                v-if="block.image"
                :src="block.image.src"
                alt=""
                class="homepage-thumb"
                loading="lazy"
              />
              <div v-else class="homepage-thumb homepage-thumb--empty">
                <q-icon name="image" color="grey-5" />
              </div>
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-weight-medium">{{ block.title }}</q-item-label>
              <q-item-label v-if="block.subtitle" caption lines="2">
                {{ block.subtitle }}
              </q-item-label>
              <q-item-label caption>
                <template v-if="block.cta_link">
                  {{ block.cta_label || 'Découvrir' }} → {{ block.cta_link }}
                </template>
                <template v-if="block.starts_at || block.ends_at">
                  · {{ windowLabel(block) }}
                </template>
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-chip
                dense
                size="sm"
                :color="status(block).color"
                text-color="white"
                :label="status(block).label"
              />
            </q-item-section>
            <q-item-section side>
              <div class="row no-wrap">
                <q-btn
                  flat
                  dense
                  icon="arrow_upward"
                  :disable="index === 0"
                  @click="move(group.blocks, index, -1)"
                >
                  <q-tooltip>Monter</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  dense
                  icon="arrow_downward"
                  :disable="index === group.blocks.length - 1"
                  @click="move(group.blocks, index, 1)"
                >
                  <q-tooltip>Descendre</q-tooltip>
                </q-btn>
                <q-btn flat dense icon="edit" color="primary" @click="openEdit(block)" />
                <q-btn flat dense icon="delete" color="grey-8" @click="remove(block)" />
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </div>
    </template>

    <q-dialog v-model="dialog">
      <q-card style="width: 720px; max-width: 95vw">
        <q-card-section class="row items-center">
          <div class="text-h6 col">{{ editingId ? 'Modifier le bloc' : 'Nouveau bloc' }}</div>
          <q-btn flat round dense icon="close" v-close-popup />
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>
              {{ dialogError }}
            </q-banner>
            <q-option-group
              v-model="form.kind"
              :options="[
                { label: 'Hero (grand bandeau du haut)', value: 'hero' },
                { label: 'Bannière', value: 'banner' },
              ]"
              inline
            />
            <q-input
              v-model="form.title"
              label="Titre *"
              outlined
              dense
              maxlength="200"
              :rules="[(v: string) => !!v.trim() || 'Titre requis']"
              data-testid="homepage-title"
            />
            <q-input
              v-model="form.subtitle"
              label="Texte"
              type="textarea"
              autogrow
              outlined
              dense
              maxlength="500"
            />
            <div class="row q-col-gutter-sm">
              <q-input
                v-model="form.cta_label"
                class="col-12 col-sm-4"
                label="Libellé du bouton"
                hint="« Voir le catalogue » par défaut"
                outlined
                dense
                maxlength="60"
              />
              <q-input
                v-model="form.cta_link"
                class="col-12 col-sm-8"
                label="Lien"
                hint="Chemin du site (/catalogue?cat=…) ou adresse https://"
                outlined
                dense
                maxlength="500"
              />
            </div>

            <div class="text-subtitle2 q-mt-md">Image</div>
            <div class="row items-center q-gutter-md">
              <img v-if="previewSrc" :src="previewSrc" alt="" class="homepage-preview" />
              <div v-else class="homepage-preview homepage-thumb--empty">
                <q-icon name="image" size="32px" color="grey-5" />
              </div>
              <div class="column q-gutter-sm">
                <q-btn
                  outline
                  color="primary"
                  icon="photo_library"
                  label="Choisir dans la médiathèque"
                  no-caps
                  data-testid="homepage-pick-image"
                  @click="pickerOpen = true"
                />
                <q-btn
                  v-if="form.media_id || form.image_url"
                  flat
                  dense
                  no-caps
                  color="grey-8"
                  label="Retirer l'image"
                  @click="clearImage"
                />
              </div>
            </div>
            <q-input
              v-if="!form.media_id"
              v-model="form.image_url"
              label="…ou URL d'une image hébergée ailleurs"
              outlined
              dense
              maxlength="500"
            />
            <q-input
              v-model="form.alt"
              label="Texte alternatif"
              hint="Décrit l'image pour les lecteurs d'écran ; laissez vide si décorative"
              outlined
              dense
              maxlength="255"
            />

            <div class="text-subtitle2 q-mt-md">Publication</div>
            <div class="row q-col-gutter-sm items-center">
              <q-toggle v-model="form.is_published" class="col-12 col-sm-4" label="Publié" />
              <q-input
                v-model="form.starts_at"
                class="col-12 col-sm-4"
                type="datetime-local"
                label="À partir du"
                stack-label
                outlined
                dense
                clearable
              />
              <q-input
                v-model="form.ends_at"
                class="col-12 col-sm-4"
                type="datetime-local"
                label="Jusqu'au"
                stack-label
                outlined
                dense
                clearable
              />
            </div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              label="Enregistrer"
              :loading="saving"
              data-testid="homepage-save"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <MediaPicker v-model="pickerOpen" kind="homepage" @select="onPick" />
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { formatDateTime } from '@app/utils';

import MediaPicker from '@/components/MediaPicker.vue';
import { extractApiError } from '@/api/errors';
import {
  createHomepageBlock,
  deleteHomepageBlock,
  listHomepageBlocks,
  saveHomepageBlock,
  type HomepageBlock,
  type HomepageBlockWrite,
} from '@/api/homepage';
import type { MediaAsset } from '@/api/media';

type Kind = 'hero' | 'banner';

const blocks = ref<HomepageBlock[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

interface BlockGroup {
  kind: Kind;
  label: string;
  blocks: HomepageBlock[];
}

const groups = computed<BlockGroup[]>(() => [
  { kind: 'hero', label: 'Hero', blocks: blocks.value.filter((b) => b.kind === 'hero') },
  {
    kind: 'banner',
    label: 'Bannières',
    blocks: blocks.value.filter((b) => b.kind === 'banner'),
  },
]);

function status(block: HomepageBlock): { label: string; color: string } {
  if (!block.is_published) return { label: 'Brouillon', color: 'grey-6' };
  const now = Date.now();
  if (block.starts_at && new Date(block.starts_at).getTime() > now) {
    return { label: 'Programmé', color: 'orange' };
  }
  if (block.ends_at && new Date(block.ends_at).getTime() <= now) {
    return { label: 'Expiré', color: 'grey-7' };
  }
  return { label: 'En ligne', color: 'green' };
}

function windowLabel(block: HomepageBlock): string {
  const from = block.starts_at ? `du ${formatDateTime(block.starts_at)}` : '';
  const to = block.ends_at ? `jusqu'au ${formatDateTime(block.ends_at)}` : '';
  return [from, to].filter(Boolean).join(' ');
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    blocks.value = await listHomepageBlocks();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
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
}

const form = reactive<BlockForm>(emptyForm('banner'));

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
  };
}

/** ISO (UTC) → valeur d'un champ datetime-local, dans le fuseau du navigateur. */
function toLocalInput(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function fromLocalInput(value: string | null): string | null {
  return value ? new Date(value).toISOString() : null;
}

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
  const sameKind = blocks.value.filter((b) => b.kind === kind);
  form.position = sameKind.length ? Math.max(...sameKind.map((b) => b.position ?? 0)) + 1 : 0;
  pickedPreview.value = null;
  dialogError.value = null;
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
    starts_at: toLocalInput(block.starts_at),
    ends_at: toLocalInput(block.ends_at),
  });
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
    position: form.position,
    is_published: form.is_published,
    starts_at: fromLocalInput(form.starts_at),
    ends_at: fromLocalInput(form.ends_at),
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
    notice.value = 'Bloc enregistré.';
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

function writeOf(block: HomepageBlock, position: number): HomepageBlockWrite {
  return {
    kind: block.kind,
    title: block.title,
    subtitle: block.subtitle ?? null,
    cta_label: block.cta_label ?? null,
    cta_link: block.cta_link ?? null,
    media_id: block.media_id ?? null,
    image_url: block.image_url ?? null,
    alt: block.alt ?? null,
    position,
    is_published: block.is_published ?? false,
    starts_at: block.starts_at ?? null,
    ends_at: block.ends_at ?? null,
  };
}

/** Échange deux blocs voisins, puis renumérote le groupe (0, 1, 2…). */
async function move(list: HomepageBlock[], index: number, delta: number) {
  const reordered = [...list];
  const [item] = reordered.splice(index, 1);
  if (!item) return;
  reordered.splice(index + delta, 0, item);
  error.value = null;
  try {
    await Promise.all(reordered.map((b, i) => saveHomepageBlock(b.id, writeOf(b, i))));
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Réordonnancement impossible.';
  }
}

async function remove(block: HomepageBlock) {
  error.value = null;
  try {
    await deleteHomepageBlock(block.id);
    notice.value = `« ${block.title} » supprimé.`;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Suppression impossible.';
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
  background: #f1f1f3;

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
  border-radius: 8px;
  background: #f1f1f3;
}
</style>
