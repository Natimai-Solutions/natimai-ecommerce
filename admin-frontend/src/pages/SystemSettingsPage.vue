<template>
  <q-page class="admin-page">
    <PageHeader
      title="Paramètres"
      hint="Les réglages de la boutique, modifiables sans redéploiement. Une valeur laissée vide reprend celle de l'environnement ou le défaut."
    >
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          label="Actualiser"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>
    <AppNotice v-if="notice" tone="success" dense class="q-mb-md">{{ notice }}</AppNotice>

    <div class="row items-center q-mb-md" style="gap: 8px">
      <q-input
        v-model="search"
        outlined
        dense
        clearable
        placeholder="Rechercher un réglage"
        style="min-width: 260px"
        data-testid="settings-search"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
    </div>

    <div v-if="loading && !rows.length" class="text-center q-pa-xl">
      <q-spinner size="2.5em" />
    </div>

    <div v-else class="settings-layout">
      <nav v-if="!search" class="settings-nav" aria-label="Catégories">
        <button
          v-for="cat in visibleCategories"
          :key="cat.key"
          type="button"
          class="settings-nav__item"
          :class="{ 'settings-nav__item--active': cat.key === activeCategory }"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
          <span class="settings-nav__count">{{ byCategory(cat.key).length }}</span>
        </button>
      </nav>

      <div class="settings-main">
        <section v-for="cat in shownCategories" :key="cat.key" class="app-section">
          <div class="app-section__head">
            <h2 class="app-section__title">{{ cat.label }}</h2>
          </div>
          <p class="admin-hint q-mt-none">{{ cat.hint }}</p>

          <div
            v-for="setting in filtered(cat.key)"
            :key="setting.key"
            class="setting"
            :data-testid="`setting-${setting.key}`"
          >
            <div class="setting__text">
              <div class="setting__label">
                {{ setting.label }}
                <StatusTag
                  :label="SOURCE_LABELS[setting.source]"
                  :tone="setting.source === 'db' ? 'ok' : 'neutral'"
                />
                <StatusTag v-if="setting.reprices" label="Recalcule les prix" tone="warn" />
                <StatusTag v-if="setting.restart_required" label="Redémarrage requis" tone="warn" />
                <StatusTag v-if="setting.public" label="Public" tone="neutral" />
              </div>
              <div v-if="setting.description" class="setting__help">{{ setting.description }}</div>
              <div class="setting__meta text-subtle">
                <span class="font-mono">{{ setting.key }}</span>
                <template v-if="setting.env_var">
                  · variable <span class="font-mono">{{ setting.env_var }}</span></template
                >
                <template v-if="setting.source === 'db' && setting.fallback">
                  · sans valeur saisie : {{ setting.fallback || '—' }}</template
                >
                <template v-if="setting.updated_at && setting.source === 'db'">
                  · modifié le {{ formatDate(setting.updated_at) }}
                  <template v-if="setting.updated_by_email">
                    par {{ setting.updated_by_email }}</template
                  >
                </template>
              </div>
              <AppNotice v-if="setting.stored_invalid" tone="warning" dense class="q-mt-xs">
                La valeur enregistrée n'est plus valable : la valeur de repli s'applique.
              </AppNotice>
            </div>

            <div class="setting__control">
              <q-toggle
                v-if="setting.type === 'bool'"
                :model-value="draft[setting.key] === 'true'"
                :disable="busy === setting.key"
                :aria-label="setting.label"
                @update:model-value="(on: boolean) => save(setting, on ? 'true' : 'false')"
              />
              <div v-else class="setting__row">
                <q-select
                  v-if="setting.choices"
                  v-model="draft[setting.key]"
                  :options="setting.choices"
                  outlined
                  dense
                  :aria-label="setting.label"
                  class="setting__input"
                />
                <q-input
                  v-else
                  v-model="draft[setting.key]"
                  outlined
                  dense
                  :type="inputType(setting)"
                  :autogrow="setting.type === 'text'"
                  :inputmode="isNumeric(setting) ? 'decimal' : undefined"
                  :placeholder="setting.secret ? 'Non renseigné' : setting.fallback"
                  :suffix="setting.unit ?? undefined"
                  :maxlength="setting.max_length ?? undefined"
                  :hint="rangeHint(setting)"
                  :aria-label="setting.label"
                  class="setting__input"
                  @keyup.enter="setting.type !== 'text' && save(setting, draft[setting.key] ?? '')"
                />
                <q-btn
                  color="primary"
                  unelevated
                  no-caps
                  label="Enregistrer"
                  :disable="!isDirty(setting)"
                  :loading="busy === setting.key"
                  class="setting__save"
                  @click="save(setting, draft[setting.key] ?? '')"
                />
              </div>
              <q-btn
                v-if="setting.source === 'db' || setting.stored_invalid"
                flat
                no-caps
                dense
                size="sm"
                icon="ph:arrow-counter-clockwise"
                label="Valeur par défaut"
                :disable="busy === setting.key"
                @click="reset(setting)"
              />
            </div>
          </div>
          <p v-if="!filtered(cat.key).length" class="text-subtle">Aucun réglage.</p>
        </section>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { intlLocale } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  listSettingCategories,
  listSystemSettings,
  resetSystemSetting,
  updateSystemSetting,
  type RuntimeSetting,
  type SettingCategory,
} from '@/api/systemSettings';
import { extractApiError } from '@/api/errors';

const SOURCE_LABELS: Record<RuntimeSetting['source'], string> = {
  db: 'Saisi ici',
  env: 'Environnement',
  default: 'Défaut',
};

const rows = ref<RuntimeSetting[]>([]);
const categories = ref<SettingCategory[]>([]);
const draft = reactive<Record<string, string>>({});
const loading = ref(false);
const busy = ref<string | null>(null);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const search = ref<string | null>('');
const activeCategory = ref<string>('');

function byCategory(key: string): RuntimeSetting[] {
  return rows.value.filter((r) => r.category === key).sort((a, b) => a.order - b.order);
}

const visibleCategories = computed(() =>
  categories.value.filter((c) => byCategory(c.key).length > 0),
);

function matches(setting: RuntimeSetting, needle: string): boolean {
  const text = `${setting.label} ${setting.description} ${setting.key}`.toLowerCase();
  return text.includes(needle);
}

function filtered(key: string): RuntimeSetting[] {
  const needle = (search.value ?? '').trim().toLowerCase();
  return needle ? byCategory(key).filter((s) => matches(s, needle)) : byCategory(key);
}

const shownCategories = computed(() => {
  if ((search.value ?? '').trim()) {
    return visibleCategories.value.filter((c) => filtered(c.key).length > 0);
  }
  return visibleCategories.value.filter((c) => c.key === activeCategory.value);
});

/** Ce que le champ affiche : la valeur saisie, sinon vide (le repli en indice). */
function editable(setting: RuntimeSetting): string {
  if (setting.type === 'bool') return setting.value;
  return setting.source === 'db' ? setting.value : '';
}

function isNumeric(setting: RuntimeSetting): boolean {
  return ['int', 'float', 'decimal'].includes(setting.type);
}

function inputType(setting: RuntimeSetting): 'text' | 'textarea' | 'password' {
  if (setting.secret) return 'password';
  return setting.type === 'text' ? 'textarea' : 'text';
}

function rangeHint(setting: RuntimeSetting): string | undefined {
  if (!isNumeric(setting)) return setting.type === 'list' ? 'Séparés par des virgules' : undefined;
  const parts: string[] = [];
  if (setting.minimum !== null) parts.push(`min ${Number(setting.minimum)}`);
  if (setting.maximum !== null) parts.push(`max ${Number(setting.maximum)}`);
  if (setting.below !== null) parts.push(`< ${Number(setting.below)}`);
  return parts.length ? parts.join(' · ') : undefined;
}

function isDirty(setting: RuntimeSetting): boolean {
  return (draft[setting.key] ?? '') !== editable(setting);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString(intlLocale(), { dateStyle: 'short', timeStyle: 'short' });
}

function apply(updated: RuntimeSetting) {
  const index = rows.value.findIndex((r) => r.key === updated.key);
  if (index >= 0) rows.value.splice(index, 1, updated);
  draft[updated.key] = editable(updated);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [settings, cats] = await Promise.all([listSystemSettings(), listSettingCategories()]);
    rows.value = settings;
    categories.value = cats;
    for (const s of settings) draft[s.key] = editable(s);
    if (!visibleCategories.value.some((c) => c.key === activeCategory.value)) {
      activeCategory.value = visibleCategories.value[0]?.key ?? '';
    }
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function save(setting: RuntimeSetting, value: string) {
  busy.value = setting.key;
  error.value = null;
  notice.value = null;
  try {
    const updated = await updateSystemSetting(setting.key, { value });
    apply(updated);
    notice.value = updated.reprices
      ? `« ${updated.label} » enregistré : les prix du catalogue sont en cours de recalcul.`
      : `« ${updated.label} » enregistré.`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement impossible.';
    draft[setting.key] = editable(setting);
  } finally {
    busy.value = null;
  }
}

async function reset(setting: RuntimeSetting) {
  busy.value = setting.key;
  error.value = null;
  notice.value = null;
  try {
    apply(await resetSystemSetting(setting.key));
    notice.value = `« ${setting.label} » : retour à la valeur par défaut.`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Réinitialisation impossible.';
  } finally {
    busy.value = null;
  }
}

onMounted(load);
</script>

<style scoped>
.settings-layout {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.settings-nav {
  flex: 0 0 210px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: sticky;
  top: 16px;
}

.settings-nav__item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.settings-nav__item:hover {
  background: var(--n-surface-2, rgba(127, 127, 127, 0.08));
}

.settings-nav__item--active {
  background: var(--n-surface-2, rgba(127, 127, 127, 0.14));
  font-weight: 600;
}

.settings-nav__count {
  font-size: 12px;
  opacity: 0.6;
}

.settings-main {
  flex: 1 1 auto;
  min-width: 0;
}

.setting {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
  padding: 14px 0;
  border-top: 1px solid var(--n-border, rgba(127, 127, 127, 0.18));
}

.setting__text {
  flex: 1 1 320px;
  min-width: 0;
}

.setting__label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.setting__help {
  margin-top: 4px;
  font-size: 13px;
}

.setting__meta {
  margin-top: 4px;
  font-size: 12px;
  word-break: break-word;
}

.setting__control {
  flex: 0 1 380px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
}

.setting__row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.setting__input {
  flex: 1 1 auto;
  min-width: 0;
}

.setting__save {
  flex: none;
  height: 40px;
}

@media (max-width: 760px) {
  .settings-layout {
    flex-direction: column;
  }

  .settings-nav {
    position: static;
    flex: none;
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
  }

  .settings-nav__item {
    white-space: nowrap;
    gap: 6px;
  }
}
</style>
