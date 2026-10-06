<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('specs.title')" :hint="$t('specs.hint')">
      <template #actions>
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('specs.new')"
          @click="openCreate()"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-categories="props">
        <q-td :props="props">
          <q-chip
            v-for="id in props.row.category_ids"
            :key="id"
            dense
            icon="ph:folders"
            :label="categoryName(id)"
          />
          <q-chip
            v-for="c in props.row.categories"
            :key="`kw-${c}`"
            dense
            outline
            icon="ph:storefront"
            :label="c"
          >
            <q-tooltip>{{ $t('specs.keyword_tip') }}</q-tooltip>
          </q-chip>
          <span
            v-if="props.row.categories.length === 0 && props.row.category_ids.length === 0"
            class="text-subtle"
            >{{ $t('specs.all_categories') }}</span
          >
        </q-td>
      </template>
      <template #body-cell-aliases="props">
        <q-td :props="props">
          <span class="text-muted">{{
            $t('specs.n_aliases', { n: props.row.aliases.length })
          }}</span>
        </q-td>
      </template>
      <template #body-cell-is_active="props">
        <q-td :props="props" align="center">
          <StatusTag
            v-if="props.row.is_active"
            :label="$t('specs.active')"
            tone="ok"
            icon="ph:check-circle"
          />
          <StatusTag v-else :label="$t('specs.inactive')" tone="neutral" icon="ph:minus-circle" />
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="no-wrap">
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_active"
            flat
            round
            dense
            icon="ph:trash"
            color="negative"
            @click="confirmDelete(props.row)"
          >
            <q-tooltip>{{ $t('specs.disable') }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('specs.none') }}</div>
      </template>
    </q-table>

    <!-- Create / edit dialog -->
    <q-dialog
      :model-value="dialog"
      :persistent="guard.persistent.value"
      @update:model-value="guard.onToggle"
    >
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editingKey ? $t('specs.edit_title', { key: editingKey }) : $t('specs.new_title') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.key"
              :label="$t('specs.key')"
              outlined
              dense
              :readonly="!!editingKey"
              :rules="req"
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
              v-model="texts.label_fr"
              :label="$t('specs.label_fr')"
              outlined
              dense
              :rules="content.isSource.value ? req : []"
            />
            <q-select
              v-model="form.type"
              :options="typeOptions"
              :label="$t('specs.type')"
              outlined
              dense
              emit-value
              map-options
              :rules="req"
            />
            <q-input v-model="form.unit" :label="$t('specs.unit')" outlined dense bottom-slots />
            <q-select
              v-model="form.category_ids"
              :options="categoryOptions"
              :label="$t('specs.category_ids')"
              :hint="$t('specs.category_ids_hint')"
              outlined
              dense
              multiple
              use-chips
              emit-value
              map-options
              bottom-slots
              data-testid="spec-categories"
            />
            <q-select
              v-model="form.categories"
              :label="$t('specs.categories')"
              :hint="$t('specs.categories_hint')"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              bottom-slots
              :options="[]"
            />
            <q-select
              v-model="form.aliases"
              :label="$t('specs.aliases')"
              outlined
              dense
              multiple
              use-input
              use-chips
              hide-dropdown-icon
              new-value-mode="add-unique"
              bottom-slots
              :options="[]"
            />
            <q-toggle v-if="editingKey" v-model="form.is_active" :label="$t('specs.active')" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="guard.requestClose()" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="editingKey ? $t('specs.save') : $t('specs.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Delete confirm -->
    <q-dialog v-model="deleteDialog">
      <q-card class="app-dialog app-dialog--narrow">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('specs.disable_q') }}</h2>
          <p class="app-dialog__text">
            {{ $t('specs.key_short') }} <span class="font-mono">{{ toDelete?.key }}</span>
          </p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
          <q-btn
            flat
            no-caps
            :label="$t('specs.disable')"
            color="negative"
            :loading="deleting"
            @click="performDelete"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import ContentLanguageTabs from '@/components/ContentLanguageTabs.vue';
import { useDialogGuard, useFormSnapshot } from '@/composables/useUnsavedGuard';
import {
  cloneTranslations,
  useContentTranslations,
  type Translations,
} from '@/composables/useContentTranslations';
import {
  createSpecDefinition,
  deleteSpecDefinition,
  listSpecDefinitions,
  updateSpecDefinition,
  type SpecDefinition,
} from '@/api/specDefinitions';
import { extractApiError } from '@/api/errors';
import { listAdminCategories, type AdminCategory } from '@/api/categories';

const { t } = useI18n();
const route = useRoute();

const rows = ref<SpecDefinition[]>([]);
/** Shop categories a definition can be attached to (active, not merged). */
const categories = ref<AdminCategory[]>([]);
const categoryOptions = computed(() =>
  categories.value
    .filter((c) => !c.merged_into_id)
    .map((c) => ({ label: c.title, value: c.id })),
);
function categoryName(id: string): string {
  return categories.value.find((c) => c.id === id)?.title ?? '?';
}
const loading = ref(false);
const error = ref<string | null>(null);

const req = [
  (v: string | number | null | undefined) =>
    (v !== null && v !== undefined && String(v).length > 0) || t('common.required'),
];
const typeOptions = computed(() => [
  { label: t('specs.numeric'), value: 'numeric' },
  { label: t('specs.enum'), value: 'enum' },
]);

const columns = computed<QTableColumn[]>(() => [
  { name: 'key', label: t('specs.col_key'), field: 'key', align: 'left', classes: 'font-mono' },
  { name: 'label_fr', label: t('specs.col_label'), field: 'label_fr', align: 'left' },
  { name: 'type', label: t('specs.col_type'), field: 'type', align: 'left' },
  { name: 'unit', label: t('specs.col_unit'), field: (r) => r.unit ?? '—', align: 'left' },
  { name: 'categories', label: t('specs.col_categories'), field: 'categories', align: 'left' },
  { name: 'aliases', label: t('specs.col_aliases'), field: 'aliases', align: 'left' },
  { name: 'is_active', label: t('specs.col_status'), field: 'is_active', align: 'center' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [specs, cats] = await Promise.all([listSpecDefinitions(), listAdminCategories()]);
    rows.value = specs;
    categories.value = cats;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

const dialog = ref(false);
const editingKey = ref<string | null>(null);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive<{
  key: string;
  label_fr: string;
  type: string;
  unit: string;
  category_ids: string[];
  categories: string[];
  aliases: string[];
  is_active: boolean;
  translations: Translations;
}>({
  key: '',
  label_fr: '',
  type: 'numeric',
  unit: '',
  category_ids: [],
  categories: [],
  aliases: [],
  is_active: true,
  translations: {},
});
const content = useContentTranslations({
  form,
  fields: ['label_fr'],
  status: () => rows.value.find((r) => r.key === editingKey.value)?.translation_status,
});
const texts = content.texts;
// Unsaved edits are not lost on Escape, backdrop or navigation (R9 / T5).
const snapshot = useFormSnapshot(() => form);
const guard = useDialogGuard({
  isOpen: () => dialog.value,
  close: () => (dialog.value = false),
  isDirty: snapshot.isDirty,
});

function openCreate(categoryId: string | null = null) {
  dialogError.value = null;
  editingKey.value = null;
  form.key = '';
  form.label_fr = '';
  form.type = 'numeric';
  form.unit = '';
  form.category_ids = categoryId ? [categoryId] : [];
  form.categories = [];
  form.aliases = [];
  form.is_active = true;
  form.translations = {};
  content.reset();
  snapshot.take();
  dialog.value = true;
}

function openEdit(spec: SpecDefinition) {
  dialogError.value = null;
  editingKey.value = spec.key;
  form.key = spec.key;
  form.label_fr = spec.label_fr;
  form.type = spec.type;
  form.unit = spec.unit ?? '';
  form.category_ids = [...(spec.category_ids ?? [])];
  form.categories = [...spec.categories];
  form.aliases = [...spec.aliases];
  form.is_active = spec.is_active;
  form.translations = cloneTranslations(spec.translations);
  content.reset();
  snapshot.take();
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    if (editingKey.value) {
      await updateSpecDefinition(editingKey.value, {
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        category_ids: form.category_ids,
        categories: form.categories,
        aliases: form.aliases,
        is_active: form.is_active,
        translations: form.translations,
      });
    } else {
      await createSpecDefinition({
        key: form.key,
        label_fr: form.label_fr,
        type: form.type,
        unit: form.unit || null,
        category_ids: form.category_ids,
        categories: form.categories,
        aliases: form.aliases,
        translations: form.translations,
      });
    }
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

const deleteDialog = ref(false);
const deleting = ref(false);
const toDelete = ref<SpecDefinition | null>(null);

function confirmDelete(spec: SpecDefinition) {
  toDelete.value = spec;
  deleteDialog.value = true;
}

async function performDelete() {
  if (!toDelete.value) return;
  deleting.value = true;
  try {
    await deleteSpecDefinition(toDelete.value.key);
    deleteDialog.value = false;
    toDelete.value = null;
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('specs.disable_failed');
    deleteDialog.value = false;
  } finally {
    deleting.value = false;
  }
}

onMounted(async () => {
  await load();
  // Opened from the product form (« Définir les caractéristiques de cette
  // catégorie ») : the new definition is pre-attached to that category.
  const wanted = typeof route.query.category === 'string' ? route.query.category : null;
  if (wanted && categories.value.some((c) => c.id === wanted)) openCreate(wanted);
});
</script>
