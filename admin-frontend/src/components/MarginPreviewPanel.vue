<template>
  <section class="margin-panel" aria-live="polite" data-testid="margin-panel">
    <div class="margin-panel__head">
      <h4 class="margin-panel__title">Marge</h4>
      <q-spinner v-if="loading" size="14px" />
    </div>
    <p v-if="error" class="margin-panel__note text-negative">{{ error }}</p>
    <template v-else-if="preview">
      <dl class="margin-panel__grid">
        <dt>Prix de vente TTC</dt>
        <dd class="font-mono">{{ money(preview.price_incl_tax) }}</dd>
        <dt>TVA {{ pct(preview.tax_rate_pct) }}</dt>
        <dd class="font-mono">− {{ money(preview.tax_amount) }}</dd>
        <dt>Prix HT</dt>
        <dd class="font-mono">{{ money(preview.price_excl_tax) }}</dd>
        <template v-if="Number(preview.commission_amount ?? 0) > 0">
          <dt>Commission de paiement</dt>
          <dd class="font-mono">− {{ money(preview.commission_amount) }}</dd>
        </template>
        <dt>Coût de revient HT</dt>
        <dd class="font-mono">
          {{ preview.unit_cost === null ? '—' : `− ${money(preview.unit_cost)}` }}
        </dd>
      </dl>
      <div
        v-if="preview.margin_amount !== null"
        class="margin-panel__result"
        :class="{ 'margin-panel__result--loss': Number(preview.margin_amount) < 0 }"
      >
        <span>Marge HT</span>
        <strong class="font-mono" data-testid="margin-amount">{{
          money(preview.margin_amount)
        }}</strong>
        <span class="margin-panel__rates">
          <span data-testid="margin-pct">taux de marque {{ pct(preview.margin_pct) }}</span>
          ·
          <span>taux de marge {{ pct(preview.markup_pct) }}</span>
        </span>
      </div>
      <p v-if="preview.note" class="margin-panel__note">
        <q-icon name="ph:info" /> {{ preview.note }}
      </p>

      <div v-if="preview.groups.length > 1" class="margin-panel__groups" data-testid="group-prices">
        <h4 class="margin-panel__title">Prix par groupe de clients</h4>
        <table class="margin-panel__table">
          <thead>
            <tr>
              <th>Groupe</th>
              <th>Prix TTC saisi</th>
              <th>Prix payé</th>
              <th>Marge HT</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="line in preview.groups"
              :key="line.price_group_id"
              :data-testid="`group-price-row-${line.label}`"
            >
              <td>
                {{ line.label }}
                <div class="text-caption text-subtle">
                  <template v-if="line.is_default">prix de référence</template>
                  <template v-else-if="Number(line.discount_pct) > 0">
                    remise {{ pct(line.discount_pct) }}
                  </template>
                  <template v-else>sans remise</template>
                </div>
              </td>
              <td>
                <q-input
                  v-if="!line.is_default"
                  :model-value="groupPrices?.[line.price_group_id] ?? ''"
                  type="number"
                  min="0"
                  step="1"
                  dense
                  outlined
                  clearable
                  :placeholder="line.typed_price === null ? money(line.price) : ''"
                  class="margin-panel__input font-mono"
                  :data-testid="`group-price-input-${line.label}`"
                  @update:model-value="(v) => setGroupPrice(line.price_group_id, v)"
                />
                <span v-else class="text-subtle">—</span>
              </td>
              <td class="font-mono" :data-testid="`group-price-paid-${line.label}`">
                {{ money(line.price) }}
              </td>
              <td
                class="font-mono"
                :class="{ 'text-negative': Number(line.margin_amount ?? 0) < 0 }"
              >
                {{ line.margin_amount === null ? '—' : money(line.margin_amount) }}
                <span v-if="line.margin_pct !== null" class="text-caption text-subtle">
                  {{ pct(line.margin_pct) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="margin-panel__note">
          Vide = prix de référence moins la remise du groupe (Groupes tarifaires).
        </p>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue';

import { formatMoney } from '@app/utils';
import { extractApiError } from '@/api/errors';
import { previewMargin, type MarginPreview, type MarginPreviewRequest } from '@/api/margin';

/**
 * Prix HT, coût de revient et marge des valeurs du formulaire article,
 * recalculés par le serveur (même formule que le catalogue) à chaque saisie.
 */
const props = defineProps<{
  input: MarginPreviewRequest;
  /** Prix saisis par groupe (group id → prix TTC) ; null = pas encore chargés. */
  groupPrices?: Record<string, string> | null;
}>();
const emit = defineEmits<{ 'update:groupPrices': [value: Record<string, string>] }>();

function setGroupPrice(groupId: string, value: string | number | null) {
  const next = { ...(props.groupPrices ?? {}) };
  const text = value === null ? '' : String(value).trim();
  if (text === '') delete next[groupId];
  else next[groupId] = text;
  emit('update:groupPrices', next);
}

const preview = ref<MarginPreview | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
let timer: ReturnType<typeof setTimeout> | null = null;
let sequence = 0;

function money(value: string | null): string {
  return value === null ? '—' : formatMoney(value, preview.value?.currency ?? 'XPF');
}

function pct(value: string | null): string {
  if (value === null) return '—';
  return `${Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`;
}

async function refresh() {
  const current = ++sequence;
  loading.value = true;
  try {
    const result = await previewMargin(props.input);
    if (current !== sequence) return;
    preview.value = result;
    error.value = null;
  } catch (err) {
    if (current !== sequence) return;
    error.value = extractApiError(err) ?? 'Marge indisponible.';
  } finally {
    if (current === sequence) loading.value = false;
  }
}

watch(
  () => JSON.stringify(props.input),
  () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void refresh(), 300);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer);
});
</script>

<style scoped>
.margin-panel {
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-tile);
  padding: 12px 14px;
  margin: 4px 0 12px;
}

.margin-panel__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.margin-panel__title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--n-ink-2);
}

.margin-panel__grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 2px 16px;
  margin: 0;
  font-size: 13px;
}

.margin-panel__grid dt {
  color: var(--n-ink-2);
}

.margin-panel__grid dd {
  margin: 0;
  text-align: right;
}

.margin-panel__result {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--n-line);
}

.margin-panel__result strong {
  font-size: 18px;
  color: var(--n-ok);
}

.margin-panel__result--loss strong {
  color: var(--n-danger);
}

.margin-panel__rates {
  font-size: 13px;
  color: var(--n-ink-2);
}

.margin-panel__groups {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--n-line);
}

.margin-panel__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-top: 6px;
}

.margin-panel__table th {
  text-align: left;
  font-weight: 500;
  color: var(--n-ink-2);
  padding: 4px 6px;
}

.margin-panel__table td {
  padding: 4px 6px;
  vertical-align: middle;
}

.margin-panel__input {
  max-width: 130px;
}

.margin-panel__note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--n-ink-2);
}
</style>
