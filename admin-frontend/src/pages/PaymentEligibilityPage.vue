<template>
  <q-page class="admin-page">
    <PageHeader
      title="Moyens de paiement"
      hint="Méthodes proposées aux clients, ouverture par groupe tarifaire et politique d'acompte."
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

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner size="2.5em" />
    </div>

    <template v-else>
      <section class="app-section" aria-labelledby="eligibility-title">
        <div class="app-section__head">
          <h2 id="eligibility-title" class="app-section__title">Ouverture par groupe</h2>
        </div>
        <p class="admin-hint">
          Le commutateur <strong>Activé</strong> coupe/rétablit une méthode
          <strong>globalement</strong> (masquée pour tous les clients si désactivée). Les cases
          cochent les groupes autorisés : <strong>aucune coche</strong> = méthode ouverte à
          <strong>tous</strong> les groupes.
        </p>

        <q-markup-table flat bordered separator="cell">
          <thead>
            <tr>
              <th class="text-left">Méthode</th>
              <th class="text-center">Activé</th>
              <th v-for="g in groups" :key="g.id" class="text-center">
                {{ g.label }}
                <span v-if="g.default" class="text-subtle q-ml-xs">(défaut)</span>
              </th>
              <th class="text-center">Ouverture</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in methods" :key="m.id">
              <td class="text-left">
                <div>{{ m.name }}</div>
                <div class="text-caption text-subtle font-mono">{{ m.provider_code }}</div>
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
                <StatusTag
                  v-if="(eligible[m.id]?.length ?? 0) === 0"
                  tone="ok"
                  icon="ph:users-three"
                  label="Tous"
                />
                <StatusTag v-else tone="warn" icon="ph:lock-simple" label="Restreinte" />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>

      <!-- Deposit policy per price group (« acompte à la commande ») -->
      <section class="app-section" aria-labelledby="deposit-title">
        <div class="app-section__head">
          <h2 id="deposit-title" class="app-section__title">Acompte à la commande</h2>
        </div>
        <p class="admin-hint">
          Par groupe tarifaire : part du total versée à la commande (vide = pas d'acompte proposé),
          frais de l'option (en % du total et/ou fixes, inclus dans le total facturé), et acompte
          imposé ou laissé au choix du client. Le solde est demandé par e-mail à la réception des
          articles.
        </p>
        <AppNotice v-if="depositNotice" tone="success" dense class="q-mb-sm">
          {{ depositNotice }}
        </AppNotice>
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
              <td>
                <q-input
                  v-model="depositEdit(g).deposit_pct"
                  type="number"
                  min="1"
                  max="99"
                  dense
                  outlined
                  style="width: 90px"
                  placeholder="—"
                />
              </td>
              <td>
                <q-input
                  v-model="depositEdit(g).deposit_fee_pct"
                  type="number"
                  min="0"
                  step="0.5"
                  dense
                  outlined
                  style="width: 90px"
                />
              </td>
              <td>
                <q-input
                  v-model="depositEdit(g).deposit_fee_fixed"
                  type="number"
                  min="0"
                  dense
                  outlined
                  style="width: 110px"
                />
              </td>
              <td><q-toggle v-model="depositEdit(g).deposit_required" dense /></td>
              <td class="text-right">
                <q-btn
                  flat
                  round
                  dense
                  icon="ph:floppy-disk"
                  :loading="savingDeposit === g.id"
                  @click="saveDeposit(g)"
                >
                  <q-tooltip>Enregistrer</q-tooltip>
                </q-btn>
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
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
} from '@/api/eligibility';
import { extractApiError } from '@/api/errors';

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
