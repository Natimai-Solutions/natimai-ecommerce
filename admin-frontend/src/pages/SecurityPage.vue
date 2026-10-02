<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('security.title')" :hint="$t('security.hint')" />

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>
    <AppNotice v-if="notice" tone="success" class="q-mb-md">{{ notice }}</AppNotice>
    <AppNotice v-if="status?.required && !status.enabled" tone="warning" class="q-mb-md">
      <!-- eslint-disable-next-line vue/no-v-html -- trusted message -->
      <span v-html="$t('security.required')"></span>
    </AppNotice>

    <div v-if="loading && !status" class="text-center q-pa-xl"><q-spinner size="2.5em" /></div>

    <template v-else-if="status">
      <!-- Codes de secours affichés une seule fois -->
      <section v-if="recoveryCodes.length" class="app-section" data-testid="recovery-codes">
        <div class="app-section__head">
          <h2 class="app-section__title">{{ $t('security.codes_title') }}</h2>
        </div>
        <AppNotice tone="warning" dense class="q-mb-sm">
          {{ $t('security.codes_hint') }}
        </AppNotice>
        <div class="recovery-grid font-mono">
          <span v-for="code in recoveryCodes" :key="code">{{ code }}</span>
        </div>
        <q-btn
          flat
          no-caps
          icon="ph:check"
          :label="$t('security.noted')"
          class="q-mt-sm"
          @click="recoveryCodes = []"
        />
      </section>

      <section class="app-section">
        <div class="app-section__head">
          <h2 class="app-section__title">{{ $t('security.heading') }}</h2>
          <StatusTag
            v-if="status.enabled"
            tone="ok"
            icon="ph:shield-check"
            :label="$t('common.active_f')"
            data-testid="2fa-active"
          />
          <StatusTag v-else tone="warn" icon="ph:shield-warning" :label="$t('common.inactive_f')" />
        </div>

        <!-- Activation -->
        <template v-if="!status.enabled">
          <p v-if="!setup" class="admin-hint">
            {{ $t('security.install') }}
          </p>
          <q-btn
            v-if="!setup"
            color="primary"
            unelevated
            no-caps
            icon="ph:qr-code"
            :label="$t('security.enable')"
            :loading="busy"
            data-testid="2fa-start"
            @click="onStart"
          />
          <div v-else class="setup">
            <img :src="setup.qr_svg_data_uri" :alt="$t('security.qr_alt')" class="setup__qr" />
            <div class="setup__steps">
              <ol>
                <li>{{ $t('security.scan') }}</li>
                <li>
                  {{ $t('security.no_camera') }}
                  <span class="font-mono setup__secret">{{ groupedSecret }}</span>
                </li>
                <li>{{ $t('security.type_code') }}</li>
              </ol>
              <q-form class="row items-start" style="gap: 8px" @submit.prevent="onConfirm">
                <q-input
                  v-model="code"
                  :label="$t('security.code')"
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
                  :label="$t('security.confirm')"
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
            {{ $t('security.codes_left', { n: status.recovery_codes_left }) }}
          </p>
          <q-form class="q-gutter-sm" style="max-width: 420px" @submit.prevent>
            <q-input
              v-model="code"
              :label="$t('security.current_code')"
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
                :label="$t('security.new_codes')"
                :disable="!code.trim()"
                :loading="busy"
                @click="onRegenerate"
              />
            </div>
            <q-separator class="q-my-md" />
            <q-input
              v-model="password"
              type="password"
              :label="$t('security.password')"
              outlined
              dense
              autocomplete="current-password"
            />
            <q-btn
              flat
              no-caps
              color="negative"
              icon="ph:shield-slash"
              :label="$t('security.disable')"
              :disable="!code.trim() || !password"
              :loading="busy"
              @click="onDisable"
            />
          </q-form>
        </template>
      </section>

      <section class="app-section" data-testid="password-section">
        <div class="app-section__head">
          <h2 class="app-section__title">{{ $t('security.pw_title') }}</h2>
        </div>
        <p class="admin-hint">{{ $t('security.pw_hint') }}</p>
        <q-form class="q-gutter-sm" style="max-width: 420px" @submit.prevent="onChangePassword">
          <q-input
            v-model="pw.current"
            type="password"
            :label="$t('security.pw_current')"
            outlined
            dense
            autocomplete="current-password"
          />
          <q-input
            v-model="pw.next"
            type="password"
            :label="$t('security.pw_new')"
            :rules="[(v: string) => !v || v.length >= 8 || $t('security.pw_rule')]"
            outlined
            dense
            autocomplete="new-password"
          />
          <q-input
            v-model="pw.confirm"
            type="password"
            :label="$t('security.pw_confirm')"
            :rules="[(v: string) => !v || v === pw.next || $t('security.pw_mismatch')]"
            outlined
            dense
            autocomplete="new-password"
          />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            icon="ph:key"
            :label="$t('security.pw_submit')"
            :disable="!pw.current || pw.next.length < 8 || pw.next !== pw.confirm"
            :loading="busy"
          />
        </q-form>
      </section>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { useAuthStore } from '@/stores/auth';
import {
  changeMyPassword,
  confirmTwoFactor,
  disableTwoFactor,
  getTwoFactorStatus,
  regenerateRecoveryCodes,
  startTwoFactorSetup,
  type TwoFactorSetup,
  type TwoFactorStatus,
} from '@/api/security';

const { t } = useI18n();

const status = ref<TwoFactorStatus | null>(null);
const setup = ref<TwoFactorSetup | null>(null);
const recoveryCodes = ref<string[]>([]);
const code = ref('');
const password = ref('');
const loading = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);

const router = useRouter();
const auth = useAuthStore();
const pw = reactive({ current: '', next: '', confirm: '' });

/** Le serveur ferme toutes les sessions : on se reconnecte avec le nouveau. */
async function onChangePassword() {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    await changeMyPassword(pw.current, pw.next);
    await auth.logout();
    await router.replace({ path: '/login', query: { password_changed: '1' } });
  } catch (err) {
    error.value = extractApiError(err) ?? t('security.pw_failed');
  } finally {
    busy.value = false;
  }
}

const groupedSecret = computed(() => (setup.value?.secret.match(/.{1,4}/g) ?? []).join(' '));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await getTwoFactorStatus();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
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
  }, t('security.gen_failed'));
}

function onConfirm() {
  void run(async () => {
    recoveryCodes.value = await confirmTwoFactor(code.value.trim());
    setup.value = null;
    code.value = '';
    notice.value = t('security.enabled');
    await load();
  }, t('security.code_refused'));
}

function onRegenerate() {
  void run(async () => {
    recoveryCodes.value = await regenerateRecoveryCodes(code.value.trim());
    code.value = '';
    notice.value = t('security.regenerated');
    await load();
  }, t('security.code_refused'));
}

function onDisable() {
  void run(async () => {
    status.value = await disableTwoFactor(code.value.trim(), password.value);
    code.value = '';
    password.value = '';
    notice.value = t('security.disabled');
  }, t('security.disable_refused'));
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
