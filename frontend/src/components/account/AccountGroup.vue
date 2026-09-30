<template>
  <div>
    <div v-if="loading" aria-busy="true">
      <q-skeleton type="text" width="40%" />
      <q-skeleton type="text" width="60%" />
    </div>

    <template v-else>
      <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

      <section class="app-section">
        <div class="app-panel group__current">
          <span class="group__label">Votre groupe tarifaire</span>
          <span class="group__name">{{ options?.current_group?.label ?? 'Standard' }}</span>
          <span class="group__hint"
            >Les prix affichés sur le site tiennent compte de ce groupe.</span
          >
        </div>
      </section>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">Demander un autre groupe</h2>
          <p class="app-section__hint">
            Réservé aux professionnels et revendeurs. Notre équipe valide chaque demande.
          </p>
        </div>

        <AppNotice v-if="saved" tone="success" class="q-mb-md">
          Votre demande a été envoyée. Elle sera examinée par notre équipe.
        </AppNotice>

        <q-form v-if="selectOptions.length" class="app-form" @submit.prevent="submit">
          <q-select
            v-model="form.price_group_id"
            :options="selectOptions"
            label="Groupe souhaité"
            outlined
            emit-value
            map-options
            bottom-slots
          />
          <q-input
            v-model="form.business_registration_number"
            label="Numéro d'immatriculation (TAHITI, RCS, SIRET…)"
            outlined
            bottom-slots
          />
          <q-input
            v-model="form.attestation_notes"
            label="Informations complémentaires (facultatif)"
            type="textarea"
            autogrow
            outlined
            bottom-slots
          />
          <div class="app-form__actions">
            <q-btn
              type="submit"
              unelevated
              color="primary"
              label="Envoyer la demande"
              :loading="submitting"
              :disable="!form.price_group_id || !form.business_registration_number.trim()"
            />
          </div>
        </q-form>
        <p v-else class="text-muted">Aucun autre groupe n'est disponible à la demande.</p>
      </section>

      <section v-if="requests.length" class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">Mes demandes</h2>
        </div>
        <ul class="app-rows">
          <li v-for="req in requests" :key="req.id" class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">{{ groupLabel(req.price_group_id) }}</span>
              <span class="app-row__meta">
                Demandée le {{ formatDate(req.created_at) }}
                <template v-if="req.admin_comment"> · {{ req.admin_comment }}</template>
              </span>
            </div>
            <StatusTag :tone="STATUS[req.status].tone" :label="STATUS[req.status].label" />
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { formatDate } from '@app/utils';

import AppNotice from '@/components/AppNotice.vue';
import StatusTag from '@/components/StatusTag.vue';
import {
  getUpgradeOptions,
  listMyUpgradeRequests,
  submitUpgradeRequest,
  type GroupUpgradeRequest,
  type UpgradeGroupOptions,
  type UpgradeRequestStatus,
} from '@/api/groupUpgrade';
import { apiErrorMessage } from '@/utils/errors';
import type { StatusTone } from '@/utils/statusTone';

const STATUS: Record<UpgradeRequestStatus, { label: string; tone: StatusTone }> = {
  PENDING: { label: 'En attente', tone: 'warn' },
  APPROVED: { label: 'Approuvée', tone: 'ok' },
  REJECTED: { label: 'Refusée', tone: 'danger' },
};

const loading = ref(true);
const error = ref<string | null>(null);
const saved = ref(false);
const submitting = ref(false);
const options = ref<UpgradeGroupOptions | null>(null);
const requests = ref<GroupUpgradeRequest[]>([]);
const form = reactive({
  price_group_id: null as string | null,
  business_registration_number: '',
  attestation_notes: '',
});

const selectOptions = computed(() =>
  (options.value?.available_groups ?? []).map((g) => ({ label: g.label, value: g.id })),
);

function groupLabel(id: string): string {
  const all = [
    ...(options.value?.current_group ? [options.value.current_group] : []),
    ...(options.value?.available_groups ?? []),
  ];
  return all.find((g) => g.id === id)?.label ?? 'Groupe';
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [opts, reqs] = await Promise.all([getUpgradeOptions(), listMyUpgradeRequests()]);
    options.value = opts;
    requests.value = reqs;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? 'Impossible de charger votre groupe tarifaire.';
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!form.price_group_id || !form.business_registration_number.trim()) return;
  submitting.value = true;
  error.value = null;
  saved.value = false;
  try {
    await submitUpgradeRequest({
      price_group_id: form.price_group_id,
      business_registration_number: form.business_registration_number.trim(),
      attestation_notes: form.attestation_notes.trim() || null,
    });
    saved.value = true;
    form.price_group_id = null;
    form.business_registration_number = '';
    form.attestation_notes = '';
    await load();
  } catch (err) {
    error.value = apiErrorMessage(err) ?? "Échec de l'envoi de la demande.";
  } finally {
    submitting.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.group__current {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 560px;
}

.group__label {
  font-size: 13px;
  color: var(--n-ink-2);
}

.group__name {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.group__hint {
  font-size: 13px;
  color: var(--n-ink-3);
}
</style>
