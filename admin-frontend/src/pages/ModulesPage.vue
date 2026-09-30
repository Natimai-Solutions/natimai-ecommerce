<template>
  <q-page class="admin-page">
    <PageHeader
      title="Modules"
      hint="Allumer ou éteindre une partie de la boutique, sans redémarrage."
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

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading && !modules.length" class="text-center q-pa-xl">
      <q-spinner size="2.5em" />
    </div>

    <template v-else>
      <p class="admin-hint">
        Un module éteint masque ses écrans et ses options, refuse ses actions et met ses tâches
        planifiées en pause. <strong>Rien n'est supprimé</strong> : ses données reviennent telles
        quelles quand on le rallume. Le mode de la boutique ({{ modeLabel }}) ne fixe que la valeur
        de départ d'une installation neuve.
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
                  :label="`Bloqué par ${module.blocked_by_env}`"
                >
                </StatusTag>
                <StatusTag
                  v-else-if="module.enabled"
                  tone="ok"
                  icon="ph:check-circle"
                  label="Actif"
                />
                <StatusTag v-else tone="neutral" icon="ph:minus-circle" label="Éteint" />
              </td>
              <td class="text-center" style="width: 90px">
                <q-toggle
                  :model-value="module.switched_on"
                  :disable="updating === module.key"
                  :aria-label="`${module.label} : ${module.switched_on ? 'allumé' : 'éteint'}`"
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
import { computed, onMounted, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { listModules, setModuleEnabled, type ModuleState } from '@/api/modules';
import { extractApiError } from '@/api/errors';
import { useShopConfigStore } from '@/stores/shopConfig';

const shopConfig = useShopConfigStore();
const modules = ref<ModuleState[]>([]);
const loading = ref(false);
const updating = ref<string | null>(null);
const error = ref<string | null>(null);

const modeLabel = computed(() => (shopConfig.isSimple ? 'simple' : 'complet'));

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
    error.value = extractApiError(err) ?? 'Chargement impossible.';
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
    error.value = extractApiError(err) ?? 'Mise à jour impossible.';
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
