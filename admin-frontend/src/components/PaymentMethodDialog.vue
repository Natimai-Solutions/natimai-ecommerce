<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog app-dialog--wide" data-testid="method-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">
          {{ method ? `Modifier « ${method.name} »` : 'Nouveau moyen de paiement' }}
        </h2>
        <p class="app-dialog__text">
          <template v-if="method">
            Type <strong>{{ method.type_label }}</strong> — le type ne change pas : créez un autre
            moyen pour en changer.
          </template>
          <template v-else>
            Le type fixe le fonctionnement (carte, espèces, virement…) ; plusieurs moyens peuvent
            partager un type, par exemple deux virements vers deux banques.
          </template>
        </p>
      </q-card-section>

      <q-form @submit.prevent="submit">
        <q-card-section class="method-form">
          <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>

          <q-select
            v-if="!method"
            v-model="form.providerCode"
            :options="typeOptions"
            label="Type *"
            outlined
            dense
            emit-value
            map-options
            data-testid="method-type"
            hide-bottom-space
            :rules="[(v: string) => !!v || 'Type requis']"
          />

          <q-input
            v-model="form.name"
            label="Nom affiché au client *"
            outlined
            dense
            maxlength="100"
            data-testid="method-name"
            hide-bottom-space
            :rules="[(v: string) => !!v.trim() || 'Nom requis']"
          />
          <q-input
            v-model="form.description"
            label="Description (sous le nom, au checkout)"
            outlined
            dense
            maxlength="255"
            data-testid="method-description"
          />

          <div class="method-form__row">
            <q-input
              v-model="form.fee"
              type="number"
              min="0"
              step="1"
              :label="`Frais (${currency})`"
              outlined
              dense
              class="font-mono"
              data-testid="method-fee"
            />
            <q-input
              v-model="form.maxAmount"
              type="number"
              min="0"
              step="1"
              :label="`Plafond (${currency})`"
              hint="Vide = sans plafond"
              outlined
              dense
              class="font-mono"
              data-testid="method-max"
            />
            <q-input
              v-model.number="form.sortOrder"
              type="number"
              min="0"
              step="1"
              label="Ordre d'affichage"
              outlined
              dense
              class="font-mono"
              data-testid="method-order"
            />
          </div>

          <div class="method-form__toggles">
            <q-toggle v-model="form.active" label="Proposé aux clients" color="positive" />
            <q-toggle v-model="form.depositAllowed" label="Peut régler un acompte" />
          </div>

          <template v-if="selectedType?.supports_instructions">
            <q-input
              v-model="form.instructions"
              type="textarea"
              autogrow
              maxlength="2000"
              label="Instructions envoyées au client (IBAN, adresse du bureau…)"
              outlined
              data-testid="method-instructions"
            />
            <div class="method-form__fallback">
              <template v-if="!form.instructions.trim()">
                Laissé vide, le client reçoit le texte commun du type
                <strong>{{ selectedType.label }}</strong> (Paramètres système) :
              </template>
              <template v-else>Texte commun du type, remplacé ici :</template>
              <blockquote class="method-form__quote">
                {{ selectedType.fallback_instructions ?? '—' }}
              </blockquote>
            </div>
          </template>
          <p v-else-if="selectedType" class="text-muted method-form__note">
            <q-icon name="ph:info" /> Paiement chez le prestataire : aucune instruction n'est
            envoyée au client.
          </p>
        </q-card-section>

        <q-card-actions class="app-dialog__actions method-form__actions">
          <q-btn
            v-if="method"
            flat
            no-caps
            color="negative"
            icon="ph:trash"
            label="Supprimer"
            :disable="method.payments_count > 0 || saving"
            :loading="deleting"
            data-testid="method-delete"
            @click="confirmDelete"
          >
            <q-tooltip v-if="method.payments_count > 0">
              Déjà utilisé par {{ method.payments_count }} paiement(s) : désactivez-le plutôt.
            </q-tooltip>
          </q-btn>
          <q-space />
          <q-btn flat no-caps label="Annuler" v-close-popup />
          <q-btn
            type="submit"
            color="primary"
            unelevated
            no-caps
            :label="method ? 'Enregistrer' : 'Créer le moyen'"
            :loading="saving"
            data-testid="method-save"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useQuasar } from 'quasar';

import AppNotice from '@app/ui/AppNotice.vue';
import { extractApiError } from '@/api/errors';
import {
  createPaymentMethod,
  deletePaymentMethod,
  updatePaymentMethod,
  type PaymentMethod,
  type PaymentMethodType,
  type PaymentMethodWrite,
} from '@/api/eligibility';

/** Crée un moyen de paiement sur un type existant, ou modifie / supprime un moyen. */
const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    /** null = création. */
    method: PaymentMethod | null;
    types: PaymentMethodType[];
    currency?: string;
  }>(),
  { currency: 'XPF' },
);
const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  saved: [method: PaymentMethod];
  deleted: [methodId: string];
}>();

const $q = useQuasar();
const form = reactive({
  providerCode: '',
  name: '',
  description: '',
  fee: '0',
  maxAmount: '',
  sortOrder: null as number | null,
  active: true,
  depositAllowed: true,
  instructions: '',
});
const saving = ref(false);
const deleting = ref(false);
const error = ref<string | null>(null);

const typeOptions = computed(() => props.types.map((t) => ({ value: t.code, label: t.label })));
const selectedType = computed(() =>
  props.types.find((t) => t.code === (props.method?.provider_code ?? form.providerCode)),
);

function amount(value: string | null): string {
  return value === null ? '' : String(Number(value));
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    const m = props.method;
    Object.assign(form, {
      providerCode: m?.provider_code ?? '',
      name: m?.name ?? '',
      description: m?.description ?? '',
      fee: m ? amount(m.fee) : '0',
      maxAmount: m ? amount(m.max_amount) : '',
      sortOrder: m?.sort_order ?? null,
      active: m?.is_admin_active ?? true,
      depositAllowed: m?.deposit_allowed ?? true,
      instructions: m?.instructions ?? '',
    });
    error.value = null;
  },
);

function payload(): PaymentMethodWrite {
  const data: PaymentMethodWrite = {
    name: form.name.trim(),
    description: form.description.trim() || null,
    fee: String(Number(form.fee) || 0),
    max_amount: String(form.maxAmount).trim() === '' ? null : String(Number(form.maxAmount)),
    is_admin_active: form.active,
    deposit_allowed: form.depositAllowed,
  };
  if (form.sortOrder !== null && String(form.sortOrder) !== '') data.sort_order = form.sortOrder;
  if (selectedType.value?.supports_instructions) {
    data.instructions = form.instructions.trim() || null;
  }
  return data;
}

async function submit() {
  saving.value = true;
  error.value = null;
  try {
    const saved = props.method
      ? await updatePaymentMethod(props.method.id, payload())
      : await createPaymentMethod({
          ...payload(),
          provider_code: form.providerCode,
          name: form.name.trim(),
        });
    emit('saved', saved);
    emit('update:modelValue', false);
  } catch (err) {
    error.value = extractApiError(err) ?? "Le moyen de paiement n'a pas pu être enregistré.";
  } finally {
    saving.value = false;
  }
}

function confirmDelete() {
  const method = props.method;
  if (!method) return;
  $q.dialog({
    title: 'Supprimer le moyen de paiement',
    message: `« ${method.name} » disparaîtra du checkout et de cette liste. Continuer ?`,
    cancel: { label: 'Annuler', flat: true, noCaps: true },
    ok: { label: 'Supprimer', color: 'negative', noCaps: true, unelevated: true },
  }).onOk(() => {
    void (async () => {
      deleting.value = true;
      error.value = null;
      try {
        await deletePaymentMethod(method.id);
        emit('deleted', method.id);
        emit('update:modelValue', false);
      } catch (err) {
        error.value = extractApiError(err) ?? 'Suppression impossible.';
      } finally {
        deleting.value = false;
      }
    })();
  });
}
</script>

<style scoped>
.method-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.method-form__row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.method-form__toggles {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
}

.method-form__fallback {
  font-size: 13px;
  color: var(--n-ink-2);
  margin-top: -4px;
}

.method-form__quote {
  margin: 6px 0 0;
  padding: 8px 12px;
  border-left: 3px solid var(--n-line);
  background: var(--n-tile);
  white-space: pre-line;
  color: var(--n-ink);
}

.method-form__note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 0;
  font-size: 13px;
}

@media (max-width: 599px) {
  .method-form__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
