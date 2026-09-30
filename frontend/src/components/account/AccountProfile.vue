<template>
  <div>
    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">Profil</h2>
        <p class="app-section__hint">Ces informations figurent sur vos commandes et factures.</p>
      </div>

      <div v-if="loading" class="app-form" aria-busy="true">
        <q-skeleton type="QInput" v-for="n in 3" :key="n" class="q-mb-md" />
      </div>

      <AppNotice v-else-if="loadError" tone="error">
        {{ loadError }}
        <template #action><q-btn flat label="Réessayer" @click="load" /></template>
      </AppNotice>

      <q-form v-else class="app-form" data-testid="account-profile" @submit.prevent="saveProfile">
        <q-input
          :model-value="profile?.email ?? ''"
          label="Adresse e-mail"
          outlined
          readonly
          hint="Pour changer d'adresse e-mail, contactez-nous."
          bottom-slots
        >
          <template #append>
            <q-icon
              v-if="profile?.is_verified"
              name="ph:seal-check"
              size="20px"
              class="profile__verified"
              aria-label="Adresse vérifiée"
            />
          </template>
        </q-input>
        <q-input
          v-model="form.full_name"
          label="Nom complet"
          outlined
          autocomplete="name"
          maxlength="255"
          bottom-slots
        />
        <q-input
          v-model="form.phone"
          label="Téléphone"
          outlined
          type="tel"
          autocomplete="tel"
          maxlength="50"
          hint="Pour vous joindre au sujet d'une livraison."
          bottom-slots
        />
        <AppNotice v-if="profileError" dense tone="error">{{ profileError }}</AppNotice>
        <AppNotice v-if="profileSaved" dense tone="success">Profil enregistré.</AppNotice>
        <div class="app-form__actions">
          <q-btn
            type="submit"
            unelevated
            color="primary"
            label="Enregistrer"
            :loading="savingProfile"
            :disable="!profileDirty"
          />
          <span v-if="profile?.created_at" class="profile__since">
            Client depuis le {{ formatDate(profile.created_at) }}
          </span>
        </div>
      </q-form>
    </section>

    <section class="app-section">
      <div class="app-section__head">
        <h2 class="app-section__title">Mot de passe</h2>
        <p class="app-section__hint">
          Vous serez déconnecté de tous vos appareils et invité à vous reconnecter.
        </p>
      </div>

      <q-form class="app-form" data-testid="account-password" @submit.prevent="savePassword">
        <q-input
          v-model="password.current"
          label="Mot de passe actuel"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="current-password"
          :error="!!currentPasswordError"
          :error-message="currentPasswordError ?? undefined"
          bottom-slots
        />
        <q-input
          v-model="password.next"
          label="Nouveau mot de passe"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="new-password"
          hint="8 caractères au moins."
          :rules="[(v: string) => !v || v.length >= 8 || '8 caractères au moins.']"
          lazy-rules
          bottom-slots
        />
        <q-input
          v-model="password.confirm"
          label="Confirmer le nouveau mot de passe"
          outlined
          :type="showPasswords ? 'text' : 'password'"
          autocomplete="new-password"
          :rules="[(v: string) => !v || v === password.next || 'Les deux saisies diffèrent.']"
          lazy-rules
          bottom-slots
        />
        <q-checkbox v-model="showPasswords" label="Afficher les mots de passe" dense />
        <AppNotice v-if="passwordError" dense tone="error" class="q-mt-sm">
          {{ passwordError }}
        </AppNotice>
        <div class="app-form__actions">
          <q-btn
            type="submit"
            unelevated
            color="primary"
            label="Changer le mot de passe"
            :loading="savingPassword"
            :disable="!passwordReady"
          />
          <router-link :to="{ name: 'forgot-password' }" class="text-link">
            Mot de passe oublié ou compte Google / Microsoft ?
          </router-link>
        </div>
      </q-form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { formatDate } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import { changeMyPassword, getMyProfile, updateMyProfile, type MyProfile } from '@/api/profile';
import { useAuthStore } from '@/stores/auth';
import { apiErrorCode, apiErrorMessage } from '@/utils/errors';

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
    loadError.value = apiErrorMessage(err) ?? 'Impossible de charger votre profil.';
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
    profileError.value = apiErrorMessage(err) ?? "Échec de l'enregistrement.";
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
    const message = apiErrorMessage(err) ?? 'Le mot de passe n’a pas pu être changé.';
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
