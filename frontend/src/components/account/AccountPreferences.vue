<template>
  <div>
    <div v-if="loading" class="app-form" aria-busy="true">
      <q-skeleton v-for="n in 4" :key="n" type="text" class="q-mb-md" />
    </div>

    <template v-else>
      <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">E-mails</h2>
        </div>
        <ul class="app-rows prefs__toggles">
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">Commande et paiement</span>
              <span class="app-row__meta">Confirmation, paiement reçu, facture.</span>
            </div>
            <q-toggle
              v-model="prefs.notification_email_enabled"
              aria-label="E-mails de commande et paiement"
            />
          </li>
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">Suivi de livraison</span>
              <span class="app-row__meta">Chaque étape de l'acheminement.</span>
            </div>
            <q-toggle
              v-model="prefs.notification_shipping_steps"
              aria-label="E-mails de suivi de livraison"
            />
          </li>
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">Rappels et offres</span>
              <span class="app-row__meta">Panier oublié, offres ponctuelles.</span>
            </div>
            <q-toggle
              v-model="prefs.marketing_email_enabled"
              aria-label="Rappels commerciaux et offres"
            />
          </li>
        </ul>
      </section>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">Livraison et affichage</h2>
        </div>
        <div class="app-form">
          <q-select
            v-model="prefs.preferred_shipping_mode"
            :options="shippingModeOptions"
            label="Niveau de service import"
            hint="Proposé par défaut à la commande."
            outlined
            emit-value
            map-options
            clearable
            bottom-slots
          />
          <q-select
            v-model="prefs.default_shipping_preference"
            :options="shippingPreferenceOptions"
            label="Préférence de livraison"
            outlined
            emit-value
            map-options
            clearable
            bottom-slots
          />
          <q-select
            v-if="currencyStore.available.length > 1"
            :model-value="currencyStore.currency"
            :options="currencyStore.available"
            label="Devise d'affichage"
            :hint="`Affichage seulement : le paiement reste en ${currencyStore.reference}.`"
            outlined
            bottom-slots
            @update:model-value="onCurrencyChange"
          />
        </div>
      </section>

      <div class="app-form__actions prefs__actions">
        <q-btn
          unelevated
          color="primary"
          label="Enregistrer les préférences"
          :loading="saving"
          @click="save"
        />
        <span v-if="saved" class="prefs__saved" role="status">
          <q-icon name="ph:check" size="16px" /> Enregistré
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import AppNotice from '@/components/AppNotice.vue';
import { getMyPreferences, updateMyPreferences, type UserPreferences } from '@/api/account';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';

const currencyStore = useCurrencyStore();

const loading = ref(true);
const saving = ref(false);
const saved = ref(false);
const error = ref<string | null>(null);
const prefs = reactive<Omit<UserPreferences, 'user_id'>>({
  notification_email_enabled: true,
  notification_shipping_steps: true,
  marketing_email_enabled: true,
  default_shipping_preference: null,
  locale: null,
  currency_pref: null,
  preferred_shipping_mode: null,
});

// Les options « écologiques » ne correspondent à aucune offre documentée :
// elles ne restent proposées qu'au client qui les avait déjà choisies. La
// langue n'est plus proposée tant que l'interface n'est pas traduite.
const shippingModeOptions = computed(() => [
  { label: 'Rapide (avion)', value: 'rapide' },
  { label: 'Économique (bateau)', value: 'economique' },
  ...(prefs.preferred_shipping_mode === 'ecologique'
    ? [{ label: 'Écologique', value: 'ecologique' }]
    : []),
]);
const shippingPreferenceOptions = computed(() => [
  { label: 'La plus rapide', value: 'fastest' },
  { label: 'La moins chère', value: 'cheapest' },
  ...(prefs.default_shipping_preference === 'eco_friendly'
    ? [{ label: 'La plus écologique', value: 'eco_friendly' }]
    : []),
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const data = await getMyPreferences();
    prefs.notification_email_enabled = data.notification_email_enabled;
    prefs.notification_shipping_steps = data.notification_shipping_steps;
    prefs.marketing_email_enabled = data.marketing_email_enabled ?? true;
    prefs.default_shipping_preference = data.default_shipping_preference;
    prefs.locale = data.locale;
    prefs.currency_pref = data.currency_pref;
    prefs.preferred_shipping_mode = data.preferred_shipping_mode;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? 'Impossible de charger vos préférences.';
  } finally {
    loading.value = false;
  }
}

function onCurrencyChange(code: string) {
  void currencyStore.setCurrency(code);
}

async function save() {
  saving.value = true;
  saved.value = false;
  error.value = null;
  try {
    // La devise d'affichage se règle aussi depuis l'en-tête : on enregistre la
    // valeur en cours plutôt qu'une copie périmée.
    prefs.currency_pref = currencyStore.currency;
    await updateMyPreferences({ ...prefs });
    saved.value = true;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? "Échec de l'enregistrement.";
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.prefs__toggles {
  max-width: 640px;
}

.prefs__actions {
  margin-top: 32px;
}

.prefs__saved {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--n-ok);
}
</style>
