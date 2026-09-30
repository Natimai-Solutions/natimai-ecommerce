<template>
  <q-page class="admin-page">
    <PageHeader title="Accueil du site">
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
          label="Nouveau bloc"
          data-testid="homepage-new"
          @click="openCreate()"
        />
      </template>
    </PageHeader>

    <p class="admin-hint">
      Le <strong>hero</strong> est le grand bandeau en haut de l'accueil (le premier publié
      s'affiche, sinon un texte par défaut). Les <strong>bannières</strong> suivent, dans l'ordre
      indiqué. Un bloc programmé n'apparaît qu'entre ses dates de début et de fin.
    </p>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div v-if="loading && !blocks.length" class="text-center q-pa-lg">
      <q-spinner size="2em" />
    </div>

    <template v-else>
      <section
        v-for="group in groups"
        :key="group.kind"
        class="app-section"
        :aria-labelledby="`homepage-${group.kind}-title`"
      >
        <div class="app-section__head">
          <h2 :id="`homepage-${group.kind}-title`" class="app-section__title">
            {{ group.label }}
          </h2>
        </div>
        <div v-if="!group.blocks.length" class="app-empty">
          <q-icon name="ph:image" size="28px" class="text-subtle" />
          <h3>{{ group.kind === 'hero' ? 'Aucun hero' : 'Aucune bannière' }}</h3>
          <q-btn
            outline
            no-caps
            icon="ph:plus"
            :label="`Ajouter ${group.kind === 'hero' ? 'un hero' : 'une bannière'}`"
            @click="openCreate(group.kind)"
          />
        </div>
        <q-list v-else bordered separator class="rounded-borders">
          <q-item
            v-for="(block, index) in group.blocks"
            :key="block.id"
            data-testid="homepage-block"
          >
            <q-item-section avatar>
              <img
                v-if="block.image"
                :src="block.image.src"
                alt=""
                class="homepage-thumb"
                loading="lazy"
              />
              <div v-else class="homepage-thumb homepage-thumb--empty">
                <q-icon name="ph:image" class="text-subtle" />
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
              <StatusTag
                :label="status(block).label"
                :tone="status(block).tone"
                :icon="status(block).icon"
              />
            </q-item-section>
            <q-item-section side>
              <div class="row no-wrap">
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:arrow-up"
                  :disable="index === 0"
                  @click="move(group.blocks, index, -1)"
                >
                  <q-tooltip>Monter</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:arrow-down"
                  :disable="index === group.blocks.length - 1"
                  @click="move(group.blocks, index, 1)"
                >
                  <q-tooltip>Descendre</q-tooltip>
                </q-btn>
                <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(block)">
                  <q-tooltip>Modifier</q-tooltip>
                </q-btn>
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:trash"
                  color="negative"
                  data-testid="homepage-delete"
                  @click="remove(block)"
                >
                  <q-tooltip>Supprimer</q-tooltip>
                </q-btn>
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </section>
    </template>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head row items-center no-wrap q-gutter-x-sm">
          <h2 class="app-dialog__title col">
            {{ editingId ? 'Modifier le bloc' : 'Nouveau bloc' }}
          </h2>
          <q-btn flat round dense icon="ph:x" v-close-popup>
            <q-tooltip>Fermer</q-tooltip>
          </q-btn>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
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

            <h3 class="admin-subtitle q-mt-md">Image</h3>
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
                  label="Choisir dans la médiathèque"
                  data-testid="homepage-pick-image"
                  @click="pickerOpen = true"
                />
                <q-btn
                  v-if="form.media_id || form.image_url"
                  flat
                  dense
                  no-caps
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

            <h3 class="admin-subtitle q-mt-md">Publication</h3>
            <div class="row q-col-gutter-sm items-center">
              <q-toggle
                v-model="form.is_published"
                class="col-12 col-sm-4"
                label="Publié"
                data-testid="homepage-published"
              />
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
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps label="Annuler" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
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

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';
import { formatDateTime } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
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

function status(block: HomepageBlock): { label: string; tone: StatusTone; icon: string } {
  if (!block.is_published) {
    return { label: 'Brouillon', tone: 'neutral', icon: 'ph:pencil-simple-line' };
  }
  const now = Date.now();
  if (block.starts_at && new Date(block.starts_at).getTime() > now) {
    return { label: 'Programmé', tone: 'warn', icon: 'ph:clock' };
  }
  if (block.ends_at && new Date(block.ends_at).getTime() <= now) {
    return { label: 'Expiré', tone: 'neutral', icon: 'ph:calendar-x' };
  }
  return { label: 'En ligne', tone: 'ok', icon: 'ph:check-circle' };
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
  border-radius: 8px;
  background: var(--n-tile);
}
</style>
