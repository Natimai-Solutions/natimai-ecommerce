<template>
  <q-page class="admin-page">
    <PageHeader
      title="Sécurité du compte"
      hint="Double authentification : un code de votre téléphone en plus du mot de passe."
    />

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
    <AppNotice v-if="notice" tone="success" class="q-mb-md">{{ notice }}</AppNotice>
    <AppNotice v-if="status?.required && !status.enabled" tone="warning" class="q-mb-md">
      La double authentification est <strong>obligatoire</strong> pour administrer la boutique : les
      autres écrans restent fermés tant qu'elle n'est pas activée.
    </AppNotice>

    <div v-if="loading && !status" class="text-center q-pa-xl"><q-spinner size="2.5em" /></div>

    <template v-else-if="status">
      <!-- Codes de secours affichés une seule fois -->
      <section v-if="recoveryCodes.length" class="app-section" data-testid="recovery-codes">
        <div class="app-section__head">
          <h2 class="app-section__title">Vos codes de secours</h2>
        </div>
        <AppNotice tone="warning" dense class="q-mb-sm">
          Notez-les ou imprimez-les maintenant : ils ne seront plus jamais affichés. Chacun permet
          une connexion si vous n'avez plus votre téléphone.
        </AppNotice>
        <div class="recovery-grid font-mono">
          <span v-for="code in recoveryCodes" :key="code">{{ code }}</span>
        </div>
        <q-btn
          flat
          no-caps
          icon="ph:check"
          label="Je les ai notés"
          class="q-mt-sm"
          @click="recoveryCodes = []"
        />
      </section>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">Double authentification</h2>
          <StatusTag
            v-if="status.enabled"
            tone="ok"
            icon="ph:shield-check"
            label="Active"
            data-testid="2fa-active"
          />
          <StatusTag v-else tone="warn" icon="ph:shield-warning" label="Inactive" />
        </div>

        <!-- Activation -->
        <template v-if="!status.enabled">
          <p v-if="!setup" class="admin-hint">
            Installez une application d'authentification (Google Authenticator, Microsoft
            Authenticator, 1Password, Aegis…), puis générez le code à scanner.
          </p>
          <q-btn
            v-if="!setup"
            color="primary"
            unelevated
            no-caps
            icon="ph:qr-code"
            label="Activer la double authentification"
            :loading="busy"
            data-testid="2fa-start"
            @click="onStart"
          />
          <div v-else class="setup">
            <img :src="setup.qr_svg_data_uri" alt="QR code à scanner" class="setup__qr" />
            <div class="setup__steps">
              <ol>
                <li>Scannez ce QR code avec l'application.</li>
                <li>
                  Pas d'appareil photo ? Saisissez cette clé :
                  <span class="font-mono setup__secret">{{ groupedSecret }}</span>
                </li>
                <li>Tapez le code à 6 chiffres affiché par l'application.</li>
              </ol>
              <q-form class="row items-start" style="gap: 8px" @submit.prevent="onConfirm">
                <q-input
                  v-model="code"
                  label="Code"
                  outlined
                  dense
                  inputmode="numeric"
                  autocomplete="one-time-code"
                  style="max-width: 180px"
                  data-testid="2fa-code"
                />
                <q-btn
                  type="submit"
                  color="primary"
                  unelevated
                  no-caps
                  label="Confirmer"
                  :loading="busy"
                  :disable="!code.trim()"
                  data-testid="2fa-confirm"
                />
              </q-form>
            </div>
          </div>
        </template>

        <!-- Gestion -->
        <template v-else>
          <p class="admin-hint">
            Chaque connexion à l'administration demande le code de votre application.
            {{ status.recovery_codes_left }} code(s) de secours restant(s).
          </p>
          <q-form class="q-gutter-sm" style="max-width: 420px" @submit.prevent>
            <q-input
              v-model="code"
              label="Code actuel (ou code de secours)"
              outlined
              dense
              inputmode="numeric"
              autocomplete="one-time-code"
            />
            <div class="row" style="gap: 8px">
              <q-btn
                outline
                no-caps
                icon="ph:arrows-clockwise"
                label="Nouveaux codes de secours"
                :disable="!code.trim()"
                :loading="busy"
                @click="onRegenerate"
              />
            </div>
            <q-separator class="q-my-md" />
            <q-input
              v-model="password"
              type="password"
              label="Mot de passe (pour désactiver)"
              outlined
              dense
              autocomplete="current-password"
            />
            <q-btn
              flat
              no-caps
              color="negative"
              icon="ph:shield-slash"
              label="Désactiver la double authentification"
              :disable="!code.trim() || !password"
              :loading="busy"
              @click="onDisable"
            />
          </q-form>
        </template>
      </section>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import {
  confirmTwoFactor,
  disableTwoFactor,
  getTwoFactorStatus,
  regenerateRecoveryCodes,
  startTwoFactorSetup,
  type TwoFactorSetup,
  type TwoFactorStatus,
} from '@/api/security';

const status = ref<TwoFactorStatus | null>(null);
const setup = ref<TwoFactorSetup | null>(null);
const recoveryCodes = ref<string[]>([]);
const code = ref('');
const password = ref('');
const loading = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const groupedSecret = computed(() => (setup.value?.secret.match(/.{1,4}/g) ?? []).join(' '));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await getTwoFactorStatus();
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

async function run(action: () => Promise<void>, fallback: string) {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await action();
  } catch (err) {
    error.value = extractApiError(err) ?? fallback;
  } finally {
    busy.value = false;
  }
}

function onStart() {
  void run(async () => {
    setup.value = await startTwoFactorSetup();
    code.value = '';
  }, 'Génération impossible.');
}

function onConfirm() {
  void run(async () => {
    recoveryCodes.value = await confirmTwoFactor(code.value.trim());
    setup.value = null;
    code.value = '';
    notice.value = 'Double authentification activée.';
    await load();
  }, 'Code refusé.');
}

function onRegenerate() {
  void run(async () => {
    recoveryCodes.value = await regenerateRecoveryCodes(code.value.trim());
    code.value = '';
    notice.value = 'Nouveaux codes de secours générés : les anciens ne fonctionnent plus.';
    await load();
  }, 'Code refusé.');
}

function onDisable() {
  void run(async () => {
    status.value = await disableTwoFactor(code.value.trim(), password.value);
    code.value = '';
    password.value = '';
    notice.value = 'Double authentification désactivée.';
  }, 'Désactivation refusée.');
}

onMounted(() => void load());
</script>

<style scoped>
.setup {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: flex-start;
}

.setup__qr {
  width: 200px;
  height: 200px;
  background: #fff;
  border-radius: 8px;
}

.setup__steps {
  flex: 1 1 280px;
}

.setup__secret {
  display: inline-block;
  word-break: break-all;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--n-surface-2, rgba(127, 127, 127, 0.12));
}

.recovery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 8px;
  font-size: 15px;
}
</style>
