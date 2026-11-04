<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('eligibility.title')" :hint="$t('eligibility.hint')">
      <template #actions>
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
          :label="$t('eligibility.new')"
          data-testid="method-create"
          @click="openMethod(null)"
        />
      </template>
    </PageHeader>

    <HelpPanel :title="$t('help.payment_title')" :items="helpItems" steps storage-key="payment" />

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading" class="text-center q-pa-xl">
      <q-spinner size="2.5em" />
    </div>

    <template v-else>
      <section class="app-section" aria-labelledby="providers-title">
        <div class="app-section__head">
          <h2 id="providers-title" class="app-section__title">{{ $t('eligibility.providers') }}</h2>
        </div>
        <p class="admin-hint">
          {{ $t('eligibility.providers_hint') }}
        </p>
        <q-markup-table flat bordered data-testid="payment-providers">
          <thead>
            <tr>
              <th class="text-left">{{ $t('eligibility.provider') }}</th>
              <th class="text-center">{{ $t('eligibility.enabled') }}</th>
              <th class="text-left">{{ $t('eligibility.credentials') }}</th>
              <th class="text-left">{{ $t('eligibility.state') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="provider in providers" :key="provider.code">
              <td class="text-left">
                <div>{{ provider.label }}</div>
                <div class="text-caption text-subtle font-mono">{{ provider.code }}</div>
              </td>
              <td class="text-center">
                <q-toggle
                  :model-value="provider.enabled"
                  :disable="!provider.implemented || updatingKey === providerKey(provider.code)"
                  :data-testid="`provider-enabled-${provider.code}`"
                  @update:model-value="(val) => toggleProvider(provider, val)"
                />
              </td>
              <td class="text-left">
                <StatusTag
                  v-if="provider.credentials_present"
                  tone="ok"
                  icon="ph:key"
                  :label="$t('eligibility.present')"
                />
                <StatusTag v-else tone="warn" icon="ph:key" :label="$t('eligibility.absent')" />
              </td>
              <td class="text-left">
                <StatusTag
                  v-if="!provider.implemented"
                  tone="neutral"
                  icon="ph:hourglass"
                  :label="$t('eligibility.upcoming')"
                />
                <StatusTag
                  v-else-if="provider.available"
                  tone="ok"
                  icon="ph:check-circle"
                  :label="$t('eligibility.offered')"
                />
                <StatusTag
                  v-else
                  tone="neutral"
                  icon="ph:prohibit"
                  :label="$t('eligibility.not_offered')"
                />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>

      <section class="app-section" aria-labelledby="eligibility-title">
        <div class="app-section__head">
          <h2 id="eligibility-title" class="app-section__title">
            {{ $t('eligibility.methods') }}
          </h2>
        </div>
        <AppNotice v-if="methodNotice" tone="success" dense class="q-mb-sm">
          {{ methodNotice }}
        </AppNotice>
        <p class="admin-hint">
          <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
          <span v-html="$t('eligibility.methods_help')"></span>
        </p>

        <q-markup-table flat bordered separator="cell">
          <thead>
            <tr>
              <th class="text-left">{{ $t('eligibility.method') }}</th>
              <th class="text-center">{{ $t('eligibility.enabled') }}</th>
              <th class="text-center">{{ $t('eligibility.deposit') }}</th>
              <th v-for="g in groups" :key="g.id" class="text-center">
                {{ g.label }}
                <span v-if="g.default" class="text-subtle q-ml-xs">{{
                  $t('eligibility.default')
                }}</span>
              </th>
              <th class="text-center">{{ $t('eligibility.opening') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in methods" :key="m.id">
              <td class="text-left">
                <div class="method-cell">
                  <div>
                    <div>{{ m.name }}</div>
                    <div class="text-caption text-subtle">
                      {{ methodSummary(m) }}
                    </div>
                  </div>
                  <q-btn
                    flat
                    dense
                    round
                    size="sm"
                    icon="ph:pencil-simple"
                    :aria-label="$t('eligibility.edit_method', { name: m.name })"
                    data-testid="method-edit"
                    @click="openMethod(m)"
                  >
                    <q-tooltip>{{ $t('common.edit') }}</q-tooltip>
                  </q-btn>
                </div>
              </td>
              <td class="text-center">
                <q-toggle
                  :model-value="m.is_admin_active"
                  color="positive"
                  :disable="updatingKey === activeKey(m.id)"
                  @update:model-value="(val) => toggleActive(m, val)"
                />
              </td>
              <td class="text-center">
                <q-toggle
                  :model-value="m.deposit_allowed"
                  :disable="updatingKey === depositKey(m.id)"
                  :data-testid="`method-deposit-${m.provider_code}`"
                  @update:model-value="(val) => toggleDeposit(m, val)"
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
                  :label="$t('eligibility.all')"
                />
                <StatusTag
                  v-else
                  tone="warn"
                  icon="ph:lock-simple"
                  :label="$t('eligibility.restricted')"
                />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>

      <!-- Deposit policy per price group (« acompte à la commande ») -->
      <section class="app-section" aria-labelledby="deposit-title">
        <div class="app-section__head">
          <h2 id="deposit-title" class="app-section__title">
            {{ $t('eligibility.deposit_title') }}
          </h2>
        </div>
        <p class="admin-hint">
          {{ $t('eligibility.deposit_hint') }}
        </p>
        <AppNotice v-if="depositNotice" tone="success" dense class="q-mb-sm">
          {{ depositNotice }}
        </AppNotice>
        <q-markup-table flat bordered dense>
          <thead>
            <tr>
              <th class="text-left">{{ $t('eligibility.group') }}</th>
              <th class="text-left">{{ $t('eligibility.deposit_pct') }}</th>
              <th class="text-left">{{ $t('eligibility.fee_pct') }}</th>
              <th class="text-left">
                {{ $t('eligibility.fee_fixed', { currency: shopConfig.currency }) }}
              </th>
              <th class="text-left">{{ $t('eligibility.required') }}</th>
              <th class="text-right"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in groups" :key="g.id">
              <td class="text-left">{{ g.label }}</td>
              <td>
                <q-input
                  :aria-label="`${$t('eligibility.deposit_pct')} — ${g.label}`"
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
                  :aria-label="`${$t('eligibility.fee_pct')} — ${g.label}`"
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
                  :aria-label="`${$t('eligibility.fee_fixed', { currency: shopConfig.currency })} — ${g.label}`"
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
                  color="primary"
                  unelevated
                  dense
                  no-caps
                  :label="$t('common.save')"
                  :loading="savingDeposit === g.id"
                  @click="saveDeposit(g)"
                />
              </td>
            </tr>
          </tbody>
        </q-markup-table>
      </section>
    </template>

    <PaymentMethodDialog
      v-model="methodDialog"
      :method="editedMethod"
      :types="methodTypes"
      @saved="onMethodSaved"
      @deleted="onMethodDeleted"
    />
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useShopConfigStore } from '@/stores/shopConfig';
import { computed, onMounted, reactive, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import HelpPanel from '@/components/HelpPanel.vue';
import { paymentHelp } from '@/utils/helpTopics';
import PaymentMethodDialog from '@/components/PaymentMethodDialog.vue';
import {
  addEligibility,
  listEligibleGroups,
  listPaymentMethods,
  listPaymentMethodTypes,
  listPriceGroups,
  removeEligibility,
  setPaymentMethodActive,
  setPaymentMethodDepositAllowed,
  listPaymentProviders,
  setPaymentProviderEnabled,
  type PaymentProvider,
  updatePriceGroup,
  type PaymentMethod,
  type PaymentMethodType,
  type PriceGroup,
} from '@/api/eligibility';
import { extractApiError } from '@/api/errors';
import { formatMoney } from '@app/utils';

const { t } = useI18n();
// Aide partagée par les écrans de paiement, cet écran marqué.
const helpItems = computed(() => paymentHelp(t, 'methods'));
const shopConfig = useShopConfigStore();

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
    depositNotice.value = t('eligibility.deposit_saved', { group: g.label });
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    savingDeposit.value = null;
  }
}

const methods = ref<PaymentMethod[]>([]);
const methodTypes = ref<PaymentMethodType[]>([]);
const methodDialog = ref(false);
const editedMethod = ref<PaymentMethod | null>(null);
const methodNotice = ref<string | null>(null);

/** Type, frais et plafond, sous le nom du moyen. */
function methodSummary(m: PaymentMethod): string {
  const parts = [m.type_label];
  if (Number(m.fee) > 0)
    parts.push(t('eligibility.fee', { amount: formatMoney(m.fee, shopConfig.currency) }));
  if (m.max_amount !== null)
    parts.push(t('eligibility.up_to', { amount: formatMoney(m.max_amount, shopConfig.currency) }));
  if (m.instructions) parts.push(t('eligibility.own_instructions'));
  if (m.currencies.length)
    parts.push(t('eligibility.currencies', { list: m.currencies.join(', ') }));
  return parts.join(' · ');
}

function openMethod(m: PaymentMethod | null) {
  editedMethod.value = m;
  methodNotice.value = null;
  methodDialog.value = true;
}

async function onMethodSaved(saved: PaymentMethod) {
  await load();
  methodNotice.value = t('eligibility.saved', { name: saved.name });
}

async function onMethodDeleted() {
  const name = editedMethod.value?.name ?? t('eligibility.the_method');
  await load();
  methodNotice.value = t('eligibility.deleted', { name });
}
const providers = ref<PaymentProvider[]>([]);
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
    const [pm, pg, psp, types] = await Promise.all([
      listPaymentMethods(),
      listPriceGroups(),
      listPaymentProviders(),
      listPaymentMethodTypes(),
    ]);
    providers.value = psp;
    methodTypes.value = types;
    methods.value = pm;
    groups.value = pg;
    const entries = await Promise.all(
      pm.map(async (m) => [m.id, (await listEligibleGroups(m.id)).map((g) => g.id)] as const),
    );
    eligible.value = Object.fromEntries(entries);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
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
    error.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    updatingKey.value = null;
  }
}

function providerKey(code: string): string {
  return `provider:${code}`;
}

async function toggleProvider(provider: PaymentProvider, value: boolean) {
  updatingKey.value = providerKey(provider.code);
  error.value = null;
  try {
    providers.value = await setPaymentProviderEnabled(provider.code, value);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    updatingKey.value = null;
  }
}

function depositKey(methodId: string): string {
  return `deposit:${methodId}`;
}

async function toggleDeposit(method: PaymentMethod, value: boolean) {
  updatingKey.value = depositKey(method.id);
  error.value = null;
  try {
    await setPaymentMethodDepositAllowed(method.id, value);
    method.deposit_allowed = value;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.update_failed');
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
    error.value = extractApiError(err) ?? t('common.update_failed');
  } finally {
    updatingKey.value = null;
  }
}

onMounted(load);
</script>

<style scoped>
.method-cell {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
</style>
