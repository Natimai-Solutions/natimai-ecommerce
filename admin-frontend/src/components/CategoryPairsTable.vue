<template>
  <div class="category-pairs">
    <q-markup-table flat bordered dense data-testid="category-pairs">
      <thead>
        <tr>
          <th class="text-left">Chez le fournisseur</th>
          <th class="text-right">{{ countLabel }}</th>
          <th class="text-left">Catégorie boutique</th>
          <th class="text-left">Action</th>
          <th class="text-left">Résultat</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pair in pairs" :key="keyOf(pair)">
          <td class="text-left category-pairs__source">
            <div>{{ pair.source_category || '—' }}</div>
            <div v-if="pair.source_subcategory" class="text-caption text-subtle">
              › {{ pair.source_subcategory }}
            </div>
          </td>
          <td class="text-right">{{ pair.count }}</td>
          <td class="text-left" style="min-width: 220px">
            <q-select
              :model-value="edit(pair).category_id"
              :options="categoryOptions"
              :disable="edit(pair).action === 'skip'"
              dense
              outlined
              emit-value
              map-options
              options-dense
              use-input
              input-debounce="0"
              :label="edit(pair).category_id ? undefined : autoLabel(pair)"
              @filter="filterCategories"
              @update:model-value="(v) => change(pair, { category_id: v ?? null })"
            />
          </td>
          <td class="text-left" style="min-width: 180px">
            <q-select
              :model-value="edit(pair).action"
              :options="actionOptions"
              dense
              outlined
              emit-value
              map-options
              options-dense
              @update:model-value="(v) => change(pair, { action: v })"
            />
          </td>
          <td class="text-left">
            <StatusTag
              :label="CATEGORY_EFFECT_LABELS[pair.effect] ?? pair.effect"
              :tone="effectTone(pair.effect)"
            />
            <div v-if="pair.resolved_category_name" class="text-caption text-subtle">
              → {{ pair.resolved_category_name }}
            </div>
            <q-icon
              v-if="pair.mapping"
              name="ph:bookmark-simple"
              size="14px"
              class="text-subtle q-ml-xs"
            >
              <q-tooltip>Règle enregistrée</q-tooltip>
            </q-icon>
          </td>
        </tr>
        <tr v-if="!pairs.length">
          <td colspan="5" class="text-center text-subtle">Aucune catégorie.</td>
        </tr>
      </tbody>
    </q-markup-table>
    <div class="row items-center q-mt-sm" style="gap: 8px">
      <span class="text-caption text-subtle">
        « Au nom de la source » : une catégorie boutique portant le nom de la sous-catégorie (ou de
        la catégorie), créée au besoin.
      </span>
      <q-space />
      <q-btn
        color="primary"
        unelevated
        no-caps
        dense
        icon="ph:floppy-disk"
        :label="`Enregistrer ${changedCount} règle(s)`"
        :disable="!changedCount"
        :loading="saving"
        data-testid="category-pairs-save"
        @click="save"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import StatusTag from '@app/ui/StatusTag.vue';
import { categoryLabel, type Category } from '@/api/categories';
import {
  CATEGORY_ACTION_LABELS,
  CATEGORY_EFFECT_LABELS,
  type CategoryMappingAction,
  type CategoryMappingWrite,
  type ObservedCategory,
} from '@/api/suppliers';

const props = withDefaults(
  defineProps<{
    pairs: ObservedCategory[];
    categories: Category[];
    saving?: boolean;
    countLabel?: string;
  }>(),
  { saving: false, countLabel: 'Articles' },
);
const emit = defineEmits<{ save: [rules: CategoryMappingWrite[]] }>();

interface Edit {
  category_id: string | null;
  action: CategoryMappingAction;
}

const edits = reactive<Record<string, Edit>>({});
const changed = ref(new Set<string>());

function keyOf(pair: ObservedCategory): string {
  const norm = (v: string | null) => (v ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
  return `${norm(pair.source_category)}|${norm(pair.source_subcategory)}`;
}

function initial(pair: ObservedCategory): Edit {
  return {
    category_id: pair.mapping?.category_id ?? null,
    action: pair.mapping?.action ?? 'import',
  };
}

function edit(pair: ObservedCategory): Edit {
  const key = keyOf(pair);
  if (!edits[key]) edits[key] = initial(pair);
  return edits[key];
}

function change(pair: ObservedCategory, patch: Partial<Edit>) {
  const key = keyOf(pair);
  edits[key] = { ...edit(pair), ...patch };
  const next = new Set(changed.value);
  next.add(key);
  changed.value = next;
}

watch(
  () => props.pairs,
  () => {
    for (const key of Object.keys(edits)) delete edits[key];
    changed.value = new Set();
  },
);

const changedCount = computed(() => changed.value.size);

function autoLabel(pair: ObservedCategory): string {
  const name = (pair.source_subcategory || pair.source_category || '').trim();
  return name ? `Au nom de la source (${name})` : 'Au nom de la source';
}

const allOptions = computed(() => [
  { label: 'Au nom de la source', value: null as string | null },
  ...props.categories.map((c) => ({ label: categoryLabel(c), value: c.id })),
]);
const categoryOptions = ref(allOptions.value);
watch(allOptions, (opts) => (categoryOptions.value = opts));

function filterCategories(value: string, update: (fn: () => void) => void) {
  update(() => {
    const needle = value.trim().toLowerCase();
    categoryOptions.value = needle
      ? allOptions.value.filter((o) => o.label.toLowerCase().includes(needle))
      : allOptions.value;
  });
}

const actionOptions = (Object.keys(CATEGORY_ACTION_LABELS) as CategoryMappingAction[]).map(
  (value) => ({ value, label: CATEGORY_ACTION_LABELS[value] }),
);

function effectTone(effect: string): 'ok' | 'warn' | 'neutral' {
  if (effect === 'import') return 'ok';
  if (effect === 'draft' || effect === 'deactivate') return 'warn';
  return 'neutral';
}

function save() {
  const rules: CategoryMappingWrite[] = props.pairs
    .filter((pair) => changed.value.has(keyOf(pair)))
    .map((pair) => ({
      source_category: pair.source_category,
      source_subcategory: pair.source_subcategory,
      ...edit(pair),
    }));
  emit('save', rules);
}
</script>

<style scoped>
.category-pairs__source {
  white-space: normal;
  max-width: 260px;
}
</style>
