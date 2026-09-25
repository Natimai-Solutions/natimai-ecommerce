<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Éligibilité paiement ↔ groupe</div>
      <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
    </div>

    <div class="text-caption text-grey-7 q-mb-md">
      Le commutateur <strong>Activé</strong> coupe/rétablit une méthode <strong>globalement</strong>
      (masquée pour tous les clients si désactivée). Les cases cochent les groupes autorisés :
      <strong>aucune coche</strong> = méthode ouverte à <strong>tous</strong> les groupes.
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner color="primary" size="2.5em" />
    </div>

    <q-markup-table v-else flat bordered separator="cell">
      <thead>
        <tr>
          <th class="text-left">Méthode</th>
          <th class="text-center">Activé</th>
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
          <td class="text-center">
            <q-toggle
              :model-value="m.is_admin_active"
              color="positive"
              :disable="updatingKey === activeKey(m.id)"
              @update:model-value="(val) => toggleActive(m, val)"
            />
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

    <!-- Deposit policy per price group (« acompte à la commande ») -->
    <div v-if="!loading" class="q-mt-lg">
      <div class="text-h6 q-mb-xs">Acompte à la commande</div>
      <div class="text-caption text-grey-7 q-mb-md">
        Par groupe tarifaire : part du total versée à la commande (vide = pas d'acompte proposé),
        frais de l'option (en % du total et/ou fixes, inclus dans le total facturé), et acompte
        imposé ou laissé au choix du client. Le solde est demandé par e-mail à la réception des
        articles.
      </div>
      <q-banner v-if="depositNotice" class="bg-green-1 text-green-9 q-mb-sm" dense rounded>
        {{ depositNotice }}
      </q-banner>
      <q-markup-table flat bordered dense>
        <thead>
          <tr>
            <th class="text-left">Groupe</th>
            <th class="text-left">Acompte (%)</th>
            <th class="text-left">Frais (%)</th>
            <th class="text-left">Frais fixes (XPF)</th>
            <th class="text-left">Imposé</th>
            <th class="text-right"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in groups" :key="g.id">
            <td class="text-left">{{ g.label }}</td>
            <td><q-input v-model="depositEdit(g).deposit_pct" type="number" min="1" max="99" dense outlined style="width: 90px" placeholder="—" /></td>
            <td><q-input v-model="depositEdit(g).deposit_fee_pct" type="number" min="0" step="0.5" dense outlined style="width: 90px" /></td>
            <td><q-input v-model="depositEdit(g).deposit_fee_fixed" type="number" min="0" dense outlined style="width: 110px" /></td>
            <td><q-toggle v-model="depositEdit(g).deposit_required" dense /></td>
            <td class="text-right">
              <q-btn flat dense icon="save" color="primary" :loading="savingDeposit === g.id" @click="saveDeposit(g)" />
            </td>
          </tr>
        </tbody>
      </q-markup-table>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import {
  addEligibility,
  listEligibleGroups,
  listPaymentMethods,
  listPriceGroups,
  removeEligibility,
  setPaymentMethodActive,
  updatePriceGroup,
  type PaymentMethod,
  type PriceGroup,
} from 'src/api/eligibility';
import { extractApiError } from 'src/api/errors';

// --- Deposit policy per group ---
interface DepositEdit {
  deposit_pct: string;
  deposit_fee_pct: string;
  deposit_fee_fixed: string;
  deposit_required: boolean;
}
const depositEdits = reactive<Record<string, DepositEdit>>({});
const savingDeposit = ref<string | null>(null);
const depositNotice = ref<string | null>(null);

function depositEdit(g: PriceGroup): DepositEdit {
  const existing = depositEdits[g.id];
  if (existing) return existing;
  depositEdits[g.id] = {
    deposit_pct: g.deposit_pct === null ? '' : String(Number(g.deposit_pct)),
    deposit_fee_pct: String(Number(g.deposit_fee_pct)),
    deposit_fee_fixed: String(Number(g.deposit_fee_fixed)),
    deposit_required: g.deposit_required,
  };
  return depositEdits[g.id] as DepositEdit;
}

async function saveDeposit(g: PriceGroup) {
  const edit = depositEdit(g);
  savingDeposit.value = g.id;
  error.value = null;
  depositNotice.value = null;
  try {
    const updated = await updatePriceGroup(g.id, {
      deposit_pct: edit.deposit_pct === '' ? null : String(Number(edit.deposit_pct)),
      deposit_fee_pct: String(Number(edit.deposit_fee_pct) || 0),
      deposit_fee_fixed: String(Number(edit.deposit_fee_fixed) || 0),
      deposit_required: edit.deposit_required,
    });
    Object.assign(g, updated);
    delete depositEdits[g.id];
    depositNotice.value = `Politique d'acompte du groupe « ${g.label} » enregistrée.`;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    savingDeposit.value = null;
  }
}

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
function activeKey(methodId: string): string {
  return `active:${methodId}`;
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

async function toggleActive(method: PaymentMethod, value: boolean) {
  updatingKey.value = activeKey(method.id);
  error.value = null;
  try {
    await setPaymentMethodActive(method.id, value);
    method.is_admin_active = value;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Mise à jour impossible.';
  } finally {
    updatingKey.value = null;
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
