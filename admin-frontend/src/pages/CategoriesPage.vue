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
          <div class="text-body2">{{ props.row.title }}</div>
          <div v-if="props.row.display_name" class="text-caption text-muted">
            {{ $t('categories.supplier_name', { name: props.row.name }) }}
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
      <template #body-cell-customs="props">
        <q-td :props="props">
          <span v-if="props.row.default_customs_rate_pct" class="font-mono"
            >{{ props.row.default_customs_rate_pct }} %</span
          >
          <span v-else class="text-subtle">—</span>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <template v-if="!props.row.merged_into_id">
            <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
              <q-tooltip>{{ $t('categories.edit') }}</q-tooltip>
            </q-btn>
            <q-btn flat round dense icon="ph:git-merge" @click="openMerge(props.row)">
              <q-tooltip>{{ $t('categories.merge_into') }}</q-tooltip>
            </q-btn>
            <q-btn
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
            <q-select
              v-model="editForm.default_tax_rate_id"
              :options="taxRateOptions"
              :label="$t('categories.vat')"
              :hint="$t('categories.vat_hint')"
              outlined
              dense
              emit-value
              map-options
              clearable
              data-testid="category-tax-rate"
            />
            <q-input
              v-model="editForm.default_margin_rate_pct"
              :label="$t('categories.margin')"
              :hint="$t('categories.margin_hint')"
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
      @select="(asset) => (editForm.image_url = asset.url)"
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
import { listTaxRates, setCategoryTaxRate, type TaxRate } from '@/api/taxRates';

const { t } = useI18n();

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
const createForm = reactive({ name: '', display_name: '' });

function openCreate() {
  createForm.name = '';
  createForm.display_name = '';
  createError.value = null;
  createDialog.value = true;
}

async function submitCreate() {
  creating.value = true;
  createError.value = null;
  try {
    const created = await createAdminCategory({
      name: createForm.name.trim(),
      display_name: createForm.display_name.trim() || null,
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
  default_margin_rate_pct: string;
  default_tax_rate_id: string | null;
  translations: Translations;
  suggested_category_ids: string[];
}>({
  display_name: '',
  description: '',
  image_url: '',
  default_margin_rate_pct: '',
  default_tax_rate_id: null,
  translations: {},
  suggested_category_ids: [],
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

function openEdit(category: AdminCategory) {
  dialogError.value = null;
  editing.value = category;
  editForm.display_name = category.display_name ?? '';
  editForm.description = category.description ?? '';
  editForm.image_url = category.image_url ?? '';
  editForm.default_margin_rate_pct = category.default_margin_rate_pct ?? '';
  editForm.default_tax_rate_id = category.default_tax_rate_id ?? null;
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
    });
    if ((editing.value.default_tax_rate_id ?? null) !== editForm.default_tax_rate_id) {
      await setCategoryTaxRate(editing.value.id, editForm.default_tax_rate_id);
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
});
const mediaPickerOpen = ref(false);
</script>

<style scoped lang="scss">
.image-field__thumb {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 4px;
}
</style>
