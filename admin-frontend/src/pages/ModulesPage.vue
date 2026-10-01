<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('modules.title')" :hint="$t('modules.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('modules.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading && !modules.length" class="text-center q-pa-xl">
      <q-spinner size="2.5em" />
    </div>

    <template v-else>
      <p class="admin-hint">
        <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
        <span v-html="$t('modules.explain', { mode: modeLabel })"></span>
      </p>

      <section
        v-for="group in groups"
        :key="group.label"
        class="app-section"
        :aria-label="group.label"
      >
        <div class="app-section__head">
          <h2 class="app-section__title">{{ group.label }}</h2>
        </div>
        <q-markup-table flat bordered>
          <tbody>
            <tr v-for="module in group.modules" :key="module.key">
              <td class="text-left modules-page__desc">
                <div class="text-weight-medium">{{ module.label }}</div>
                <div class="text-caption text-subtle">{{ module.description }}</div>
              </td>
              <td class="text-left" style="width: 220px">
                <StatusTag
                  v-if="module.blocked_by_env"
                  tone="warn"
                  icon="ph:lock"
                  :label="$t('modules.blocked', { env: module.blocked_by_env })"
                >
                </StatusTag>
                <StatusTag
                  v-else-if="module.enabled"
                  tone="ok"
                  icon="ph:check-circle"
                  :label="$t('modules.on')"
                />
                <StatusTag
                  v-else
                  tone="neutral"
                  icon="ph:minus-circle"
                  :label="$t('modules.off')"
                />
              </td>
              <td class="text-center" style="width: 90px">
                <q-toggle
                  :model-value="module.switched_on"
                  :disable="updating === module.key"
                  :aria-label="
                    $t('modules.switch_aria', {
                      label: module.label,
                      state: module.switched_on ? $t('modules.state_on') : $t('modules.state_off'),
                    })
                  "
                  :data-testid="`module-${module.key}`"
                  @update:model-value="(val) => toggle(module, val)"
                />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { listModules, setModuleEnabled, type ModuleState } from '@/api/modules';
import { extractApiError } from '@/api/errors';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();

const shopConfig = useShopConfigStore();
const modules = ref<ModuleState[]>([]);
const loading = ref(false);
const updating = ref<string | null>(null);
const error = ref<string | null>(null);

const modeLabel = computed(() =>
  shopConfig.isSimple ? t('modules.mode_simple') : t('modules.mode_full'),
);

const groups = computed(() => {
  const byGroup = new Map<string, ModuleState[]>();
  for (const module of modules.value) {
    byGroup.set(module.group, [...(byGroup.get(module.group) ?? []), module]);
  }
  return [...byGroup].map(([label, items]) => ({ label, modules: items }));
});

async function load() {
  loading.value = true;
  error.value = null;
  try {
    modules.value = await listModules();
  } catch (err) {
    error.value = extractApiError(err) ?? t('modules.load_failed');
  } finally {
    loading.value = false;
  }
}

async function toggle(module: ModuleState, value: boolean) {
  updating.value = module.key;
  error.value = null;
  try {
    const saved = await setModuleEnabled(module.key, value);
    modules.value = modules.value.map((m) => (m.key === saved.key ? saved : m));
    await shopConfig.reload();
  } catch (err) {
    error.value = extractApiError(err) ?? t('modules.update_failed');
  } finally {
    updating.value = null;
  }
}

onMounted(() => {
  void shopConfig.load();
  void load();
});
</script>

<style scoped>
.modules-page__desc {
  white-space: normal;
}
</style>
