<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Éligibilité paiement ↔ groupe</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Cochez les groupes autorisés pour chaque méthode. <strong>Aucune coche</strong> sur une ligne
      = méthode ouverte à <strong>tous</strong> les groupes (aucune restriction).
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner color="primary" size="2.5em" />
    </div>

    <q-markup-table v-else flat bordered separator="cell">
      <thead>
        <tr>
          <th class="text-left">Méthode</th>
          <th v-for="g in groups" :key="g.id" class="text-center">
            {{ g.label }}
            <q-badge v-if="g.default" color="grey-6" class="q-ml-xs" label="défaut" />
          </th>
          <th class="text-center">Ouverture</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in methods" :key="m.id">
          <td class="text-left">
            <div>{{ m.name }}</div>
            <div class="text-caption text-grey-6">{{ m.provider_code }}</div>
          </td>
          <td v-for="g in groups" :key="g.id" class="text-center">
            <q-checkbox
              :model-value="isEligible(m.id, g.id)"
              :disable="updatingKey === cellKey(m.id, g.id)"
              @update:model-value="(val) => toggle(m.id, g.id, val)"
            />
          </td>
          <td class="text-center">
            <q-chip
              v-if="(eligible[m.id]?.length ?? 0) === 0"
              dense
              color="green"
              text-color="white"
              label="tous"
            />
            <q-chip v-else dense color="orange" text-color="white" label="restreinte" />
          </td>
        </tr>
      </tbody>
    </q-markup-table>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import {
  addEligibility,
  listEligibleGroups,
  listPaymentMethods,
  listPriceGroups,
  removeEligibility,
  type PaymentMethod,
  type PriceGroup,
} from 'src/api/eligibility';
import { extractApiError } from 'src/api/errors';

const methods = ref<PaymentMethod[]>([]);
const groups = ref<PriceGroup[]>([]);
/** methodId → list of eligible group ids (empty = open to all). */
const eligible = ref<Record<string, string[]>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const updatingKey = ref<string | null>(null);

function cellKey(methodId: string, groupId: string): string {
  return `${methodId}:${groupId}`;
}
function isEligible(methodId: string, groupId: string): boolean {
  return eligible.value[methodId]?.includes(groupId) ?? false;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [pm, pg] = await Promise.all([listPaymentMethods(), listPriceGroups()]);
    methods.value = pm;
    groups.value = pg;
    const entries = await Promise.all(
      pm.map(async (m) => [m.id, (await listEligibleGroups(m.id)).map((g) => g.id)] as const),
    );
    eligible.value = Object.fromEntries(entries);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function toggle(methodId: string, groupId: string, value: boolean) {
  updatingKey.value = cellKey(methodId, groupId);
  error.value = null;
  try {
    if (value) {
      await addEligibility(methodId, groupId);
    } else {
      await removeEligibility(methodId, groupId);
    }
    eligible.value[methodId] = (await listEligibleGroups(methodId)).map((g) => g.id);
  } catch (err) {
    error.value = extractApiError(err) ?? 'Mise à jour impossible.';
  } finally {
    updatingKey.value = null;
  }
}

onMounted(load);
</script>
