<template>
  <div>
    <div v-if="loading" class="app-form" aria-busy="true">
      <q-skeleton v-for="n in 4" :key="n" type="text" class="q-mb-md" />
    </div>

    <template v-else>
      <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">{{ $t('prefs.emails') }}</h2>
        </div>
        <ul class="app-rows prefs__toggles">
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">{{ $t('prefs.order') }}</span>
              <span class="app-row__meta">{{ $t('prefs.order_meta') }}</span>
            </div>
            <q-toggle
              v-model="prefs.notification_email_enabled"
              :aria-label="$t('prefs.order_aria')"
            />
          </li>
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">{{ $t('prefs.shipping') }}</span>
              <span class="app-row__meta">{{ $t('prefs.shipping_meta') }}</span>
            </div>
            <q-toggle
              v-model="prefs.notification_shipping_steps"
              :aria-label="$t('prefs.shipping_aria')"
            />
          </li>
          <li class="app-row">
            <div class="app-row__main">
              <span class="app-row__title">{{ $t('prefs.marketing') }}</span>
              <span class="app-row__meta">{{ $t('prefs.marketing_meta') }}</span>
            </div>
            <q-toggle
              v-model="prefs.marketing_email_enabled"
              :aria-label="$t('prefs.marketing_aria')"
            />
          </li>
        </ul>
      </section>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">{{ $t('prefs.display') }}</h2>
        </div>
        <div class="app-form">
          <q-select
            v-model="prefs.preferred_shipping_mode"
            :options="shippingModeOptions"
            :label="$t('prefs.service')"
            :hint="$t('prefs.service_hint')"
            outlined
            emit-value
            map-options
            clearable
            bottom-slots
          />
          <q-select
            v-model="prefs.default_shipping_preference"
            :options="shippingPreferenceOptions"
            :label="$t('prefs.preference')"
            outlined
            emit-value
            map-options
            clearable
            bottom-slots
          />
          <q-select
            v-if="localeOptions.length > 1"
            :model-value="currentLocale"
            :options="localeOptions"
            :label="$t('common.language')"
            :hint="$t('prefs.lang_hint')"
            outlined
            emit-value
            map-options
            bottom-slots
            data-testid="prefs-locale"
            @update:model-value="onLocaleChange"
          />
          <q-select
            v-if="currencyStore.available.length > 1"
            :model-value="currencyStore.currency"
            :options="currencyStore.available"
            :label="$t('prefs.currency')"
            :hint="$t('prefs.currency_hint', { currency: currencyStore.reference })"
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
          :label="$t('prefs.save')"
          :loading="saving"
          @click="save"
        />
        <span v-if="saved" class="prefs__saved" role="status">
          <q-icon name="ph:check" size="16px" /> {{ $t('prefs.saved') }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useLocale } from '@/composables/useLocale';
import { computed, onMounted, reactive, ref } from 'vue';

import AppNotice from '@app/ui/AppNotice.vue';
import { getMyPreferences, updateMyPreferences, type UserPreferences } from '@/api/account';
import { useCurrencyStore } from '@/stores/currency';
import { apiErrorMessage } from '@/utils/errors';

const { t } = useI18n();
const { current: currentLocale, options: localeOptions, setLocale, adoptPreference } = useLocale();

function onLocaleChange(code: string) {
  prefs.locale = code;
  void setLocale(code);
}

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
// langue s'applique tout de suite (cookie) et est gardée sur le compte.
const shippingModeOptions = computed(() => [
  { label: t('prefs.mode.rapide'), value: 'rapide' },
  { label: t('prefs.mode.economique'), value: 'economique' },
  ...(prefs.preferred_shipping_mode === 'ecologique'
    ? [{ label: t('prefs.mode.ecologique'), value: 'ecologique' }]
    : []),
]);
const shippingPreferenceOptions = computed(() => [
  { label: t('prefs.pref.fastest'), value: 'fastest' },
  { label: t('prefs.pref.cheapest'), value: 'cheapest' },
  ...(prefs.default_shipping_preference === 'eco_friendly'
    ? [{ label: t('prefs.pref.eco'), value: 'eco_friendly' }]
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
    adoptPreference(data.locale);
    prefs.currency_pref = data.currency_pref;
    prefs.preferred_shipping_mode = data.preferred_shipping_mode;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('prefs.load_failed');
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
    prefs.locale = currentLocale.value;
    await updateMyPreferences({ ...prefs });
    saved.value = true;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('prefs.save_failed');
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
