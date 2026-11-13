<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('categories.title')">
      <template #hint>
        {{ $t('categories.hint') }}
      </template>
      <template #actions>
        <q-toggle v-model="showMerged" :label="$t('categories.show_merged')" />
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('categories.new')"
          data-testid="category-create"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <q-table
      :rows="visibleRows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-title="props">
        <q-td :props="props">
          <!-- Arbre : une sous-catégorie est décalée sous son parent. -->
          <div
            class="category-row"
            :style="{ paddingLeft: `${Math.min(props.row.depth, 6) * 20}px` }"
            :data-depth="props.row.depth"
          >
            <q-icon
              v-if="props.row.depth > 0"
              name="ph:arrow-elbow-down-right"
              size="14px"
              class="text-subtle q-mr-xs"
            />
            <div>
              <div class="text-body2">
                {{ props.row.title }}
                <span v-if="props.row.children_count" class="text-caption text-muted">
                  · {{ $t('categories.children_n', { n: props.row.children_count }) }}
                </span>
              </div>
              <div v-if="props.row.display_name" class="text-caption text-muted">
                {{ $t('categories.supplier_name', { name: props.row.name }) }}
              </div>
              <div v-if="props.row.depth > 0" class="text-caption text-subtle">
                {{ props.row.path.slice(0, -1).join(' › ') }}
              </div>
            </div>
          </div>
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            v-if="props.row.merged_into_id"
            tone="neutral"
            icon="ph:git-merge"
            :label="$t('categories.merged_into', { name: props.row.merged_into_name ?? '?' })"
          />
          <StatusTag
            v-else-if="props.row.is_active"
            tone="ok"
            icon="ph:check-circle"
            :label="$t('categories.active')"
          />
          <StatusTag
            v-else
            tone="neutral"
            icon="ph:minus-circle"
            :label="$t('categories.inactive')"
          />
        </q-td>
      </template>
      <template #body-cell-sources="props">
        <q-td :props="props">
          <div v-if="props.row.supplier_sources.length" class="category-sources">
            <q-chip
              v-for="source in props.row.supplier_sources"
              :key="source"
              dense
              size="sm"
              icon="ph:storefront"
              :label="source"
            />
          </div>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-customs="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct" class="font-mono"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <span
            v-else-if="props.row.inherited_customs_rate_pct"
            class="font-mono text-muted"
            :title="
              $t('categories.inherited_from', { name: props.row.inherited_customs_rate_from })
            "
            >{{ props.row.inherited_customs_rate_pct }} %
            <q-icon name="ph:arrow-bend-left-up" size="12px"
          /></span>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-tax="props">
        <q-td :props="props">
          <span v-if="props.row.default_tax_rate_id">{{
            taxLabel(props.row.default_tax_rate_id)
          }}</span>
          <span
            v-else-if="props.row.inherited_tax_rate_id"
            class="text-muted"
            :title="$t('categories.inherited_from', { name: props.row.inherited_tax_rate_from })"
            >{{ taxLabel(props.row.inherited_tax_rate_id) }}
            <q-icon name="ph:arrow-bend-left-up" size="12px"
          /></span>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-margin="props">
        <q-td :props="props">
          <span v-if="props.row.default_margin_rate_pct" class="font-mono"
            >{{ props.row.default_margin_rate_pct }} %</span
          >
          <span
            v-else-if="props.row.inherited_margin_rate_pct"
            class="font-mono text-muted"
            :title="$t('categories.inherited_from', { name: props.row.inherited_margin_rate_from })"
            >{{ props.row.inherited_margin_rate_pct }} %
            <q-icon name="ph:arrow-bend-left-up" size="12px"
          /></span>
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <template v-if="!props.row.merged_into_id">
            <q-btn
              :aria-label="$t('categories.edit')"
              flat
              round
              dense
              icon="ph:pencil-simple"
              @click="openEdit(props.row)"
            >
              <q-tooltip>{{ $t('categories.edit') }}</q-tooltip>
            </q-btn>
            <q-btn
              :aria-label="$t('categories.merge_into')"
              flat
              round
              dense
              icon="ph:git-merge"
              @click="openMerge(props.row)"
            >
              <q-tooltip>{{ $t('categories.merge_into') }}</q-tooltip>
            </q-btn>
            <q-btn
              :aria-label="props.row.is_active ? $t('categories.disable') : $t('categories.enable')"
              flat
              round
              dense
              :icon="props.row.is_active ? 'ph:eye-slash' : 'ph:eye'"
              :color="props.row.is_active ? 'negative' : undefined"
              :loading="busyIds.has(props.row.id)"
              @click="onToggleActive(props.row)"
            >
              <q-tooltip>{{
                props.row.is_active ? $t('categories.disable') : $t('categories.enable')
              }}</q-tooltip>
            </q-btn>
          </template>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('categories.none') }}</div>
      </template>
    </q-table>

    <div class="text-caption text-muted q-mt-sm">
      {{ $t('categories.count', { n: visibleRows.length }) }}
    </div>

    <!-- Édition -->
    <q-dialog
      :model-value="editDialog"
      :persistent="guard.persistent.value"
      @update:model-value="guard.onToggle"
    >
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ editing?.name }}</h2>
          <p class="app-dialog__text">{{ $t('categories.sync_safe') }}</p>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <ContentLanguageTabs
              v-model="content.lang.value"
              :source="content.source.value"
              :locales="content.locales.value"
              :status-of="content.statusOf"
              :reviewed="content.reviewed.value"
              @review="content.markReviewed"
            />
            <q-input
              v-model="texts.display_name"
              :label="$t('categories.shop_title')"
              :hint="$t('categories.title_hint', { name: editing?.name ?? '' })"
              outlined
              dense
              clearable
            />
            <q-input
              v-model="texts.description"
              :label="$t('categories.description')"
              type="textarea"
              autogrow
              outlined
              dense
            />
            <q-select
              v-model="editForm.parent_id"
              :options="parentOptions"
              :label="$t('categories.parent')"
              :hint="$t('categories.parent_hint')"
              emit-value
              map-options
              outlined
              dense
              clearable
              use-input
              input-debounce="0"
              data-testid="category-parent"
              @filter="filterParents"
            />
            <q-select
              v-model="editForm.suggested_category_ids"
              :options="suggestionOptions"
              :label="$t('categories.suggested')"
              :hint="$t('categories.suggested_hint')"
              emit-value
              map-options
              multiple
              use-chips
              outlined
              dense
              clearable
              data-testid="category-suggested"
            />
            <q-input
              v-model="editForm.image_url"
              :label="$t('categories.tile')"
              :hint="$t('categories.tile_hint')"
              outlined
              dense
            >
              <template v-if="editForm.image_url" #prepend>
                <img :src="editForm.image_url" alt="" class="image-field__thumb" />
              </template>
              <template #append>
                <q-btn
                  flat
                  dense
                  no-caps
                  icon="ph:images"
                  :label="$t('categories.media')"
                  @click="mediaPickerOpen = true"
                />
              </template>
            </q-input>
            <q-input
              v-if="imageMediaId"
              v-model="editForm.image_alt"
              :label="$t('categories.image_alt')"
              :hint="$t('categories.image_alt_hint')"
              outlined
              dense
              bottom-slots
              data-testid="category-image-alt"
            />
            <q-select
              v-model="editForm.default_tax_rate_id"
              :options="taxRateOptions"
              :label="$t('categories.vat')"
              :hint="inheritedHint('tax') ?? $t('categories.vat_hint')"
              outlined
              dense
              emit-value
              map-options
              clearable
              data-testid="category-tax-rate"
            />
            <q-input
              v-if="customsOn"
              v-model="editForm.default_customs_rate_pct"
              :label="$t('categories.customs')"
              :hint="inheritedHint('customs') ?? $t('categories.customs_hint')"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
              clearable
              data-testid="category-customs-rate"
            />
            <q-input
              v-model="editForm.default_margin_rate_pct"
              :label="$t('categories.margin')"
              :hint="inheritedHint('margin') ?? $t('categories.margin_hint')"
              type="number"
              step="0.01"
              min="0"
              outlined
              dense
            />
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
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Fusion -->
    <q-dialog v-model="mergeDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ $t('categories.merge_title', { title: merging?.title }) }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submitMerge">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-select
              v-model="mergeTarget"
              :options="mergeTargets"
              :label="$t('categories.target')"
              outlined
              dense
              emit-value
              map-options
              use-input
              input-debounce="0"
              @filter="filterTargets"
            />
            <AppNotice tone="warning" dense>
              <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
              <span
                v-html="$t('categories.merge_notice', { n: merging?.product_count ?? 0 })"
              ></span>
            </AppNotice>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="negative"
              unelevated
              no-caps
              :label="$t('categories.merge')"
              :loading="saving"
              :disable="!mergeTarget"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
    <q-dialog v-model="createDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('categories.new_title') }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="createError" tone="error" dense>{{ createError }}</AppNotice>
            <q-input
              v-model="createForm.name"
              :label="$t('categories.name')"
              :hint="$t('categories.key_hint')"
              outlined
              dense
              autofocus
              :rules="[(v: string) => !!v?.trim() || $t('common.required')]"
              data-testid="category-create-name"
            />
            <q-input
              v-model="createForm.display_name"
              :label="$t('categories.shop_title')"
              :hint="$t('categories.name_hint')"
              outlined
              dense
            />
            <q-select
              v-model="createForm.parent_id"
              :options="parentOptions"
              :label="$t('categories.parent')"
              :hint="$t('categories.parent_hint')"
              emit-value
              map-options
              outlined
              dense
              clearable
              use-input
              input-debounce="0"
              data-testid="category-create-parent"
              @filter="filterParents"
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn v-close-popup flat no-caps :label="$t('common.cancel')" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('categories.create')"
              :loading="creating"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
    <MediaPicker
      v-model="mediaPickerOpen"
      kind="category"
      @select="onPickImage"
      @updated="onMediaUpdated"
    />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { intlLocale } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import MediaPicker from '@/components/MediaPicker.vue';
import { getMedia, updateMedia, type MediaAsset } from '@/api/media';
import { mediaIdFromUrl } from '@/utils/media';
import ContentLanguageTabs from '@/components/ContentLanguageTabs.vue';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';
import {
  cloneTranslations,
  useContentTranslations,
  type Translations,
} from '@/composables/useContentTranslations';
import PageHeader from '@/components/PageHeader.vue';
import {
  createAdminCategory,
  listAdminCategories,
  mergeCategory,
  updateAdminCategory,
  type AdminCategory,
} from '@/api/categories';
import { extractApiError } from '@/api/errors';
import {
  listTaxRates,
  setCategoryCustomsRate,
  setCategoryTaxRate,
  type TaxRate,
} from '@/api/taxRates';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();
const shopConfig = useShopConfigStore();
/** The customs module decides whether a customs rate is asked here. */
const customsOn = computed(() => shopConfig.moduleOn('customs'));

const rows = ref<AdminCategory[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const showMerged = ref(false);

const visibleRows = computed(() =>
  showMerged.value ? rows.value : rows.value.filter((c) => !c.merged_into_id),
);

const columns = computed<QTableColumn[]>(() => [
  { name: 'title', label: t('categories.col_category'), field: 'title', align: 'left' },
  { name: 'status', label: t('categories.col_status'), field: 'is_active', align: 'left' },
  {
    name: 'product_count',
    label: t('categories.col_products'),
    field: 'product_count',
    align: 'right',
    classes: 'font-mono',
  },
  { name: 'sources', label: t('categories.col_sources'), field: 'supplier_sources', align: 'left' },
  {
    name: 'customs',
    label: t('categories.col_customs'),
    field: 'default_customs_rate_pct',
    align: 'left',
  },
  {
    name: 'tax',
    label: t('categories.col_vat'),
    field: (r) => taxLabel(r.default_tax_rate_id),
    align: 'left',
  },
  {
    name: 'margin',
    label: t('categories.col_margin'),
    field: (r) => (r.default_margin_rate_pct ? `${r.default_margin_rate_pct} %` : '—'),
    align: 'left',
  },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

const createDialog = ref(false);
const creating = ref(false);
const createError = ref<string | null>(null);
const createForm = reactive<{ name: string; display_name: string; parent_id: string | null }>({
  name: '',
  display_name: '',
  parent_id: null,
});

function openCreate() {
  createForm.name = '';
  createForm.display_name = '';
  createForm.parent_id = null;
  createError.value = null;
  parentOptions.value = allParents();
  createDialog.value = true;
}

// --- Hiérarchie : parents proposés (actives, non fusionnées, hors la
// catégorie éditée et ses sous-catégories, qui boucleraient).
const parentOptions = ref<{ label: string; value: string }[]>([]);

function descendantsOf(id: string): Set<string> {
  const out = new Set<string>();
  let frontier = [id];
  while (frontier.length) {
    const next: string[] = [];
    for (const row of rows.value) {
      if (row.parent_id && frontier.includes(row.parent_id) && !out.has(row.id)) {
        out.add(row.id);
        next.push(row.id);
      }
    }
    frontier = next;
  }
  return out;
}

function allParents(exclude?: string): { label: string; value: string }[] {
  const below = exclude ? descendantsOf(exclude) : new Set<string>();
  return rows.value
    .filter((c) => c.is_active && !c.merged_into_id && c.id !== exclude && !below.has(c.id))
    .map((c) => ({ label: c.path.join(' › '), value: c.id }))
    .sort((a, b) => a.label.localeCompare(b.label, 'fr'));
}

function filterParents(needle: string, update: (fn: () => void) => void) {
  update(() => {
    const q = needle.trim().toLowerCase();
    parentOptions.value = allParents(editing.value?.id).filter(
      (o) => !q || o.label.toLowerCase().includes(q),
    );
  });
}

/** « Vide : héritée de Réseau (12,5 %) » — shown under a field left blank. */
function inheritedHint(kind: 'tax' | 'customs' | 'margin'): string | null {
  const row = editing.value;
  if (!row) return null;
  if (kind === 'tax' && !editForm.default_tax_rate_id && row.inherited_tax_rate_from) {
    return t('categories.inherited_value', {
      name: row.inherited_tax_rate_from,
      value: taxLabel(row.inherited_tax_rate_id),
    });
  }
  if (kind === 'customs' && !editForm.default_customs_rate_pct && row.inherited_customs_rate_from) {
    return t('categories.inherited_value', {
      name: row.inherited_customs_rate_from,
      value: `${row.inherited_customs_rate_pct} %`,
    });
  }
  if (kind === 'margin' && !editForm.default_margin_rate_pct && row.inherited_margin_rate_from) {
    return t('categories.inherited_value', {
      name: row.inherited_margin_rate_from,
      value: `${row.inherited_margin_rate_pct} %`,
    });
  }
  return null;
}

async function submitCreate() {
  creating.value = true;
  createError.value = null;
  try {
    const created = await createAdminCategory({
      name: createForm.name.trim(),
      display_name: createForm.display_name.trim() || null,
      parent_id: createForm.parent_id,
    });
    createDialog.value = false;
    notice.value = t('categories.created', { title: created.title });
    await load();
    // Enchaîner sur la fiche complète (image, description, marge, TVA) :
    // la création ne demande que le nom, qui ne change plus ensuite.
    const row = rows.value.find((r) => r.id === created.id);
    if (row) openEdit(row);
  } catch (err) {
    createError.value = extractApiError(err) ?? t('categories.create_failed');
  } finally {
    creating.value = false;
  }
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    rows.value = await listAdminCategories();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

// Activation
const busyIds = ref(new Set<string>());

async function onToggleActive(category: AdminCategory) {
  notice.value = null;
  error.value = null;
  busyIds.value = new Set(busyIds.value).add(category.id);
  try {
    await updateAdminCategory(category.id, { is_active: !category.is_active });
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('categories.edit_failed');
  } finally {
    const next = new Set(busyIds.value);
    next.delete(category.id);
    busyIds.value = next;
  }
}

// Édition
const editDialog = ref(false);
const editing = ref<AdminCategory | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const editForm = reactive<{
  display_name: string;
  description: string;
  image_url: string;
  /** Alt text of the media-library image behind image_url (03/10/2026). */
  image_alt: string;
  default_margin_rate_pct: string;
  default_customs_rate_pct: string;
  default_tax_rate_id: string | null;
  translations: Translations;
  suggested_category_ids: string[];
  parent_id: string | null;
}>({
  display_name: '',
  description: '',
  image_url: '',
  image_alt: '',
  default_margin_rate_pct: '',
  default_customs_rate_pct: '',
  default_tax_rate_id: null,
  translations: {},
  suggested_category_ids: [],
  parent_id: null,
});

/** Categories a product of the edited one may suggest (R9 / T7): the live ones, itself excluded. */
const suggestionOptions = computed(() =>
  rows.value
    .filter((c) => c.is_active && !c.merged_into_id && c.id !== editing.value?.id)
    .map((c) => ({ value: c.id, label: c.title })),
);
const content = useContentTranslations({
  form: editForm,
  fields: ['display_name', 'description'],
  status: () => editing.value?.translation_status,
});
const texts = content.texts;
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const snapshot = useFormSnapshot(() => editForm);
const guard = useDialogGuard({
  isOpen: () => editDialog.value,
  close: () => (editDialog.value = false),
  isDirty: snapshot.isDirty,
});

// Taux de TVA en vigueur, pour le taux par défaut d'une catégorie.
const taxRates = ref<TaxRate[]>([]);
const taxRateOptions = computed(() =>
  taxRates.value.map((rate) => ({
    value: rate.id,
    label: `${rate.label} — ${Number(rate.rate_pct).toLocaleString(intlLocale())} %`,
  })),
);

function taxLabel(taxRateId: string | null | undefined): string {
  if (!taxRateId) return '—';
  const rate = taxRates.value.find((r) => r.id === taxRateId);
  return rate ? `${Number(rate.rate_pct).toLocaleString(intlLocale())} %` : '—';
}

async function loadTaxRates() {
  try {
    taxRates.value = await listTaxRates({ valid: true });
  } catch {
    // Non bloquant : le sélecteur reste vide.
  }
}

// The tile image's alt text lives on the media asset: shown and edited here
// when image_url comes from the library, saved with the category.
const imageMediaId = computed(() => mediaIdFromUrl(editForm.image_url));
const loadedImageAlt = ref('');

async function loadImageAlt(url: string | null | undefined) {
  const id = mediaIdFromUrl(url);
  if (!id) return;
  try {
    const asset = await getMedia(id);
    if (mediaIdFromUrl(editForm.image_url) !== id) return;
    editForm.image_alt = asset.alt ?? '';
    loadedImageAlt.value = asset.alt ?? '';
    snapshot.take();
  } catch {
    // An image deleted from the library: the URL stays editable as is.
  }
}

function onPickImage(asset: MediaAsset) {
  editForm.image_url = asset.url;
  editForm.image_alt = asset.alt ?? '';
  loadedImageAlt.value = asset.alt ?? '';
}

function onMediaUpdated(asset: MediaAsset) {
  if (mediaIdFromUrl(editForm.image_url) !== asset.id) return;
  editForm.image_alt = asset.alt ?? '';
  loadedImageAlt.value = asset.alt ?? '';
}

function openEdit(category: AdminCategory) {
  dialogError.value = null;
  editing.value = category;
  editForm.display_name = category.display_name ?? '';
  editForm.description = category.description ?? '';
  editForm.image_url = category.image_url ?? '';
  editForm.image_alt = '';
  loadedImageAlt.value = '';
  void loadImageAlt(category.image_url);
  editForm.default_margin_rate_pct = category.default_margin_rate_pct ?? '';
  editForm.default_customs_rate_pct = category.default_customs_rate_pct ?? '';
  editForm.default_tax_rate_id = category.default_tax_rate_id ?? null;
  editForm.parent_id = category.parent_id ?? null;
  parentOptions.value = allParents(category.id);
  editForm.translations = cloneTranslations(category.translations);
  editForm.suggested_category_ids = [...(category.suggested_category_ids ?? [])];
  content.reset();
  snapshot.take();
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await updateAdminCategory(editing.value.id, {
      display_name: (editForm.display_name ?? '').trim() || null,
      description: editForm.description.trim() || null,
      translations: editForm.translations,
      suggested_category_ids: editForm.suggested_category_ids,
      image_url: editForm.image_url.trim() || null,
      default_margin_rate_pct: String(editForm.default_margin_rate_pct ?? '').trim() || null,
      parent_id: editForm.parent_id,
    });
    if ((editing.value.default_tax_rate_id ?? null) !== editForm.default_tax_rate_id) {
      await setCategoryTaxRate(editing.value.id, editForm.default_tax_rate_id);
    }
    const customs = String(editForm.default_customs_rate_pct ?? '').trim() || null;
    if (customsOn.value && (editing.value.default_customs_rate_pct ?? null) !== customs) {
      await setCategoryCustomsRate(editing.value.id, customs);
    }
    const mediaId = imageMediaId.value;
    if (mediaId && editForm.image_alt.trim() !== loadedImageAlt.value) {
      await updateMedia(mediaId, { alt: editForm.image_alt.trim() || null });
    }
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

// Fusion
const mergeDialog = ref(false);
const merging = ref<AdminCategory | null>(null);
const mergeTarget = ref<string | null>(null);
const mergeTargets = ref<{ label: string; value: string }[]>([]);

function allTargets(): { label: string; value: string }[] {
  return rows.value
    .filter((c) => c.is_active && !c.merged_into_id && c.id !== merging.value?.id)
    .map((c) => ({ label: `${c.title} (${c.product_count})`, value: c.id }));
}

function filterTargets(needle: string, update: (fn: () => void) => void) {
  update(() => {
    const q = needle.trim().toLowerCase();
    mergeTargets.value = allTargets().filter((o) => !q || o.label.toLowerCase().includes(q));
  });
}

function openMerge(category: AdminCategory) {
  dialogError.value = null;
  merging.value = category;
  mergeTarget.value = null;
  mergeTargets.value = allTargets();
  mergeDialog.value = true;
}

async function submitMerge() {
  if (!merging.value || !mergeTarget.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    const result = await mergeCategory(merging.value.id, mergeTarget.value);
    mergeDialog.value = false;
    notice.value = t('categories.merged', {
      source: result.source.title,
      target: result.target.title,
      products: result.moved_products,
      discounts: result.moved_discounts,
    });
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('categories.merge_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void load();
  void loadTaxRates();
  void shopConfig.load();
});
const mediaPickerOpen = ref(false);
</script>

<style scoped lang="scss">
.category-row {
  display: flex;
  align-items: flex-start;
}

.category-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  max-width: 320px;
}

.image-field__thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: var(--n-radius-sm);
}
</style>
