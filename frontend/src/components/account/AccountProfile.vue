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
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { formatDate } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import { changeMyPassword, getMyProfile, updateMyProfile, type MyProfile } from '@/api/profile';
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
</script>

<style scoped lang="scss">
.profile__verified {
  color: var(--n-ok);
}

.profile__since {
  font-size: 13px;
  color: var(--n-ink-3);
}
</style>
