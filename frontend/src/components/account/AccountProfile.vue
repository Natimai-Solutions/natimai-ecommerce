<template>
  <div>
    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">{{ $t('profile.title') }}</h2>
        <p class="app-section__hint">{{ $t('profile.hint') }}</p>
      </div>

      <div v-if="loading" class="app-form" aria-busy="true">
        <q-skeleton type="QInput" v-for="n in 3" :key="n" class="q-mb-md" />
      </div>

      <AppNotice v-else-if="loadError" tone="error">
        {{ loadError }}
        <template #action><q-btn flat :label="$t('profile.retry')" @click="load" /></template>
      </AppNotice>

      <q-form v-else class="app-form" data-testid="account-profile" @submit.prevent="saveProfile">
        <q-input
          :model-value="profile?.email ?? ''"
          :label="$t('profile.email')"
          outlined
          readonly
          :hint="$t('profile.email_hint')"
          bottom-slots
        >
          <template #append>
            <q-icon
              v-if="profile?.is_verified"
              name="ph:seal-check"
              size="20px"
              class="profile__verified"
              :aria-label="$t('profile.verified')"
            />
          </template>
        </q-input>
        <q-input
          v-model="form.full_name"
          :label="$t('profile.full_name')"
          outlined
          autocomplete="name"
          maxlength="255"
          bottom-slots
        />
        <q-input
          v-model="form.phone"
          :label="$t('profile.phone')"
          outlined
          type="tel"
          autocomplete="tel"
          maxlength="50"
          :hint="$t('profile.phone_hint')"
          bottom-slots
        />
        <AppNotice v-if="profileError" dense tone="error">{{ profileError }}</AppNotice>
        <AppNotice v-if="profileSaved" dense tone="success">{{ $t('profile.saved') }}</AppNotice>
        <div class="app-form__actions">
          <q-btn
            type="submit"
            unelevated
            color="primary"
            :label="$t('profile.save')"
            :loading="savingProfile"
            :disable="!profileDirty"
          />
          <span v-if="profile?.created_at" class="profile__since">
            {{ $t('profile.since', { date: formatDate(profile.created_at) }) }}
          </span>
        </div>
      </q-form>
    </section>

    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">{{ $t('profile.password_title') }}</h2>
        <p class="app-section__hint">
          {{ $t('profile.password_hint') }}
        </p>
      </div>

      <q-form class="app-form" data-testid="account-password" @submit.prevent="savePassword">
        <q-input
          v-model="password.current"
          :label="$t('profile.current')"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="current-password"
          :error="!!currentPasswordError"
          :error-message="currentPasswordError ?? undefined"
          bottom-slots
        />
        <q-input
          v-model="password.next"
          :label="$t('profile.next')"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="new-password"
          :hint="$t('profile.min_8')"
          :rules="[(v: string) => !v || v.length >= 8 || $t('profile.min_8_rule')]"
          lazy-rules
          bottom-slots
        />
        <q-input
          v-model="password.confirm"
          :label="$t('profile.confirm')"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="new-password"
          :rules="[(v: string) => !v || v === password.next || $t('profile.mismatch')]"
          lazy-rules
          bottom-slots
        />
        <q-checkbox v-model="showPasswords" :label="$t('profile.show')" dense />
        <AppNotice v-if="passwordError" dense tone="error" class="q-mt-sm">
          {{ passwordError }}
        </AppNotice>
        <div class="app-form__actions">
          <q-btn
            type="submit"
            unelevated
            color="primary"
            :label="$t('profile.change')"
            :loading="savingPassword"
            :disable="!passwordReady"
          />
          <router-link :to="{ name: 'forgot-password' }" class="text-link">
            {{ $t('profile.forgot') }}
          </router-link>
        </div>
      </q-form>
    </section>

    <!-- R8 / U8 : the customer's data rights, in self-service. -->
    <section class="app-section" data-testid="account-privacy">
      <div class="app-section__head">
        <h2 class="app-section__title">{{ $t('profile.data_title') }}</h2>
        <p class="app-section__hint">{{ $t('profile.data_hint') }}</p>
      </div>
      <AppNotice v-if="dataError" dense tone="error" class="q-mb-sm">
        {{ dataError }}
      </AppNotice>
      <div class="app-form__actions">
        <q-btn
          outline
          color="primary"
          icon="ph:download-simple"
          :label="$t('profile.data_download')"
          :loading="downloading"
          data-testid="account-export"
          @click="downloadData"
        />
        <q-btn
          flat
          color="negative"
          icon="ph:trash"
          :label="$t('profile.delete_button')"
          data-testid="account-delete"
          @click="openDeletion"
        />
      </div>
      <p class="text-muted q-mt-sm q-mb-none">{{ $t('profile.delete_hint') }}</p>
    </section>

    <q-dialog v-model="deletion.open">
      <q-card flat class="delete-dialog">
        <q-form @submit.prevent="confirmDeletion">
          <q-card-section>
            <h2 class="delete-dialog__title">{{ $t('profile.delete_title') }}</h2>
            <p>{{ $t('profile.delete_text') }}</p>
            <q-input
              v-model="deletion.confirmation"
              outlined
              stack-label
              type="email"
              autocomplete="off"
              :label="$t('profile.delete_confirm_label', { email: profile?.email ?? '' })"
              data-testid="account-delete-email"
            />
            <q-input
              v-model="deletion.password"
              outlined
              stack-label
              type="password"
              autocomplete="current-password"
              class="q-mt-sm"
              :label="$t('profile.delete_password')"
              :hint="$t('profile.delete_password_hint')"
              data-testid="account-delete-password"
            />
            <AppNotice v-if="deletion.error" dense tone="error" class="q-mt-sm">
              {{ deletion.error }}
            </AppNotice>
          </q-card-section>
          <q-card-actions align="right" class="q-px-md q-pb-md">
            <q-btn v-close-popup flat :label="$t('common.cancel')" />
            <q-btn
              type="submit"
              unelevated
              color="negative"
              :label="$t('profile.delete_confirm')"
              :loading="deletion.saving"
              :disable="!deletionReady"
              data-testid="account-delete-confirm"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { formatDate } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import {
  changeMyPassword,
  deleteMyAccount,
  downloadMyData,
  getMyProfile,
  updateMyProfile,
  type MyProfile,
} from '@/api/profile';
import { useAuthStore } from '@/stores/auth';
import { apiErrorCode, apiErrorMessage } from '@/utils/errors';

const { t } = useI18n();

const emit = defineEmits<{ updated: [profile: MyProfile] }>();

const router = useRouter();
const authStore = useAuthStore();

const profile = ref<MyProfile | null>(null);
const loading = ref(true);
const loadError = ref<string | null>(null);
const form = reactive({ full_name: '', phone: '' });
const savingProfile = ref(false);
const profileError = ref<string | null>(null);
const profileSaved = ref(false);

const profileDirty = computed(
  () =>
    !!profile.value &&
    (form.full_name.trim() !== (profile.value.full_name ?? '') ||
      form.phone.trim() !== (profile.value.phone ?? '')),
);

function fill(p: MyProfile) {
  profile.value = p;
  form.full_name = p.full_name ?? '';
  form.phone = p.phone ?? '';
}

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    fill(await getMyProfile());
  } catch (err) {
    loadError.value = apiErrorMessage(err) ?? t('profile.load_failed');
  } finally {
    loading.value = false;
  }
}

async function saveProfile() {
  savingProfile.value = true;
  profileError.value = null;
  profileSaved.value = false;
  try {
    const updated = await updateMyProfile({
      full_name: form.full_name.trim(),
      phone: form.phone.trim(),
    });
    fill(updated);
    authStore.setProfile(updated);
    profileSaved.value = true;
    emit('updated', updated);
  } catch (err) {
    profileError.value = apiErrorMessage(err) ?? t('profile.save_failed');
  } finally {
    savingProfile.value = false;
  }
}

const password = reactive({ current: '', next: '', confirm: '' });
const showPasswords = ref(false);
const savingPassword = ref(false);
const passwordError = ref<string | null>(null);
const currentPasswordError = ref<string | null>(null);

const passwordReady = computed(
  () =>
    password.current.length > 0 && password.next.length >= 8 && password.next === password.confirm,
);

async function savePassword() {
  if (!passwordReady.value) return;
  savingPassword.value = true;
  passwordError.value = null;
  currentPasswordError.value = null;
  try {
    await changeMyPassword(password.current, password.next);
    // Toutes les sessions sont fermées côté serveur, celle-ci comprise.
    await authStore.logout();
    await router.replace({
      name: 'login',
      query: { redirect: '/mon-compte', motif: 'mot-de-passe-change' },
    });
  } catch (err) {
    const message = apiErrorMessage(err) ?? t('profile.change_failed');
    if (apiErrorCode(err) === 'user.password.invalid_current') {
      currentPasswordError.value = message;
    } else {
      passwordError.value = message;
    }
  } finally {
    savingPassword.value = false;
  }
}

onMounted(load);

// --- Mes données (R8 / U8) ------------------------------------------------ //
const downloading = ref(false);
const dataError = ref<string | null>(null);

async function downloadData() {
  downloading.value = true;
  dataError.value = null;
  try {
    await downloadMyData();
  } catch (err) {
    dataError.value = apiErrorMessage(err) ?? t('profile.data_download_failed');
  } finally {
    downloading.value = false;
  }
}

const deletion = reactive({
  open: false,
  confirmation: '',
  password: '',
  saving: false,
  error: null as string | null,
});

const deletionReady = computed(
  () =>
    !!profile.value &&
    deletion.confirmation.trim().toLowerCase() === profile.value.email.toLowerCase(),
);

function openDeletion() {
  deletion.confirmation = '';
  deletion.password = '';
  deletion.error = null;
  deletion.open = true;
}

async function confirmDeletion() {
  if (!deletionReady.value) return;
  deletion.saving = true;
  deletion.error = null;
  try {
    await deleteMyAccount(deletion.confirmation.trim(), deletion.password);
    deletion.open = false;
    // The account no longer exists: every session is closed server-side.
    await authStore.logout();
    await router.replace({ name: 'login', query: { motif: 'compte-supprime' } });
  } catch (err) {
    deletion.error = apiErrorMessage(err) ?? t('profile.delete_failed');
  } finally {
    deletion.saving = false;
  }
}
</script>

<style scoped lang="scss">
.profile__verified {
  color: var(--n-ok);
}

.profile__since {
  font-size: 13px;
  color: var(--n-ink-3);
}

.delete-dialog {
  width: min(480px, 92vw);
  padding: 4px;
}

.delete-dialog__title {
  font-size: 1.15rem;
  margin: 0 0 8px;
}
</style>
