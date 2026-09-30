<template>
  <q-page class="admin-page">
    <PageHeader
      title="Groupes tarifaires"
      hint="Le prix de référence est celui du groupe par défaut. Chaque autre groupe paie ce prix moins sa remise, sur tous les articles ; un prix saisi pour le groupe sur un article passe avant."
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
    <AppNotice v-if="notice" tone="success" dense class="q-mb-md">{{ notice }}</AppNotice>

    <q-markup-table flat bordered data-testid="price-groups">
      <thead>
        <tr>
          <th class="text-left">Groupe</th>
          <th class="text-left">Remise sur le prix de référence</th>
          <th class="text-left">Marge des prix calculés</th>
          <th class="text-right"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.id" :data-testid="`price-group-${g.code}`">
          <td class="text-left">
            <div>
              {{ g.label }}
              <StatusTag
                v-if="g.default"
                label="Référence"
                tone="ok"
                icon="ph:star"
                class="q-ml-xs"
              />
            </div>
            <div class="text-caption text-subtle font-mono">{{ g.code }}</div>
          </td>
          <td class="text-left">
            <span v-if="g.default" class="text-muted">— (prix de référence)</span>
            <q-input
              v-else
              v-model="edit(g).discount_pct"
              type="number"
              min="0"
              max="99.99"
              step="0.5"
              suffix="%"
              outlined
              dense
              class="price-groups__input font-mono"
              :data-testid="`price-group-discount-${g.code}`"
            />
          </td>
          <td class="text-left">
            <q-input
              v-if="g.default"
              v-model="edit(g).margin_rate_pct"
              type="number"
              min="0"
              step="0.5"
              suffix="%"
              outlined
              dense
              class="price-groups__input font-mono"
            />
            <div v-if="g.default" class="text-caption text-subtle q-mt-xs">
              Appliquée si ni l'article ni sa catégorie n'ont de marge
            </div>
            <span v-else class="text-muted">celle du prix de référence</span>
          </td>
          <td class="text-right">
            <q-btn
              flat
              round
              dense
              icon="ph:floppy-disk"
              :loading="saving === g.id"
              :disable="!changed(g)"
              :data-testid="`price-group-save-${g.code}`"
              @click="save(g)"
            >
              <q-tooltip>Enregistrer</q-tooltip>
            </q-btn>
          </td>
        </tr>
      </tbody>
    </q-markup-table>

    <p class="admin-hint q-mt-md">
      Exemple : remise Professionnel de 10 % → un article à 11 600 F est vendu 10 440 F aux clients
      professionnels. Le groupe d'un client se règle dans <strong>Utilisateurs</strong> ; un
      visiteur non connecté paie le prix de référence.
    </p>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { listPriceGroups, updatePriceGroup, type PriceGroup } from '@/api/eligibility';

const groups = ref<PriceGroup[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const saving = ref<string | null>(null);

interface GroupEdit {
  discount_pct: string;
  margin_rate_pct: string;
}
const edits = reactive<Record<string, GroupEdit>>({});

function num(value: string | number | null | undefined): string {
  return String(Number(value ?? 0));
}

function edit(g: PriceGroup): GroupEdit {
  const existing = edits[g.id];
  if (existing) return existing;
  edits[g.id] = { discount_pct: num(g.discount_pct), margin_rate_pct: num(g.margin_rate_pct) };
  return edits[g.id] as GroupEdit;
}

function changed(g: PriceGroup): boolean {
  const e = edit(g);
  return (
    num(e.discount_pct) !== num(g.discount_pct) || num(e.margin_rate_pct) !== num(g.margin_rate_pct)
  );
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const list = await listPriceGroups();
    groups.value = [...list].sort((a, b) => Number(b.default) - Number(a.default));
    for (const key of Object.keys(edits)) delete edits[key];
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function save(g: PriceGroup) {
  const e = edit(g);
  saving.value = g.id;
  error.value = null;
  notice.value = null;
  try {
    const updated = await updatePriceGroup(
      g.id,
      g.default
        ? { margin_rate_pct: num(e.margin_rate_pct) }
        : { discount_pct: num(e.discount_pct) },
    );
    Object.assign(g, updated);
    delete edits[g.id];
    notice.value = g.default
      ? `Marge par défaut enregistrée (${num(updated.margin_rate_pct)} %).`
      : `Remise « ${g.label} » enregistrée : ${num(updated.discount_pct)} %.`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = null;
  }
}

onMounted(load);
</script>

<style scoped>
.price-groups__input {
  max-width: 160px;
}
</style>
