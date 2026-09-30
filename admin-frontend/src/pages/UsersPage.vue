<template>
  <q-page padding>
    <div class="row items-center q-mb-md">
      <div class="text-h6 col">Utilisateurs</div>
      <q-btn
        color="primary"
        icon="person_add"
        label="Créer un compte"
        no-caps
        @click="openCreate"
      />
    </div>

    <div class="row q-col-gutter-md q-mb-md items-end">
      <q-input
        v-model="search"
        label="Rechercher (email, nom)"
        outlined
        dense
        clearable
        debounce="300"
        class="col-12 col-md-4"
        @update:model-value="onFilterChange"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-select
        v-model="groupFilter"
        :options="groupOptions"
        label="Groupe de prix"
        outlined
        dense
        emit-value
        map-options
        class="col-12 col-md-3"
        @update:model-value="onFilterChange"
      />
      <q-select
        v-model="statusFilter"
        :options="statusOptions"
        label="Statut"
        outlined
        dense
        emit-value
        map-options
        class="col-12 col-md-3"
        @update:model-value="onFilterChange"
      />
      <div class="col-auto">
        <q-btn flat icon="refresh" label="Actualiser" :loading="loading" @click="load" />
      </div>
    </div>

    <q-banner v-if="error" class="bg-negative text-white q-mb-md" dense>{{ error }}</q-banner>
    <q-banner v-if="notice" class="bg-green-1 text-green-9 q-mb-md" dense rounded>
      {{ notice }}
    </q-banner>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :rows-per-page-options="[0]"
      hide-pagination
    >
      <template #body-cell-identity="props">
        <q-td :props="props">
          <div class="text-body2">
            {{ props.row.email }}
            <q-icon v-if="props.row.is_superuser" name="shield" color="primary" size="xs">
              <q-tooltip>Administrateur</q-tooltip>
            </q-icon>
          </div>
          <div class="text-caption text-grey-7">
            {{ [props.row.full_name, props.row.phone].filter(Boolean).join(' · ') || '—' }}
          </div>
        </q-td>
      </template>
      <template #body-cell-group="props">
        <q-td :props="props">{{ props.row.price_group_label ?? 'Par défaut' }}</q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            :color="statusOf(props.row).color"
            text-color="white"
            :label="statusOf(props.row).label"
          />
        </q-td>
      </template>
      <template #body-cell-last_login="props">
        <q-td :props="props">{{ formatDate(props.row.last_login) }}</q-td>
      </template>
      <template #body-cell-created_at="props">
        <q-td :props="props">{{ formatDate(props.row.created_at) }}</q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right">
          <q-btn flat dense icon="edit" color="primary" @click="openEdit(props.row)">
            <q-tooltip>Modifier (nom, téléphone, groupe)</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.invitation_pending && props.row.is_active"
            flat
            dense
            icon="forward_to_inbox"
            color="secondary"
            :loading="busyIds.has(props.row.id)"
            @click="onResend(props.row)"
          >
            <q-tooltip>Renvoyer l'invitation</q-tooltip>
          </q-btn>
          <q-btn
            flat
            dense
            :icon="props.row.is_active ? 'person_off' : 'person'"
            :color="props.row.is_active ? 'negative' : 'positive'"
            :loading="busyIds.has(props.row.id)"
            @click="onToggleActive(props.row)"
          >
            <q-tooltip>{{ props.row.is_active ? 'Désactiver' : 'Réactiver' }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <div class="row items-center q-mt-md">
      <div class="text-caption text-grey-7 col">{{ count }} compte(s)</div>
      <q-pagination
        v-if="totalPages > 1"
        v-model="page"
        :max="totalPages"
        :max-pages="6"
        boundary-numbers
        @update:model-value="load"
      />
    </div>

    <!-- Création -->
    <q-dialog v-model="createDialog">
      <q-card style="min-width: 420px">
        <q-card-section class="text-h6">Créer un compte</q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <div class="text-caption text-grey-7">
              Aucun mot de passe à saisir : la personne reçoit un lien pour choisir le sien (valable
              72 h).
            </div>
            <q-input
              v-model="form.email"
              label="Email *"
              type="email"
              outlined
              dense
              :rules="req"
            />
            <q-input v-model="form.full_name" label="Nom complet" outlined dense />
            <q-input v-model="form.phone" label="Téléphone" outlined dense />
            <q-select
              v-model="form.price_group_id"
              :options="groupChoices"
              label="Groupe de prix"
              outlined
              dense
              emit-value
              map-options
              clearable
            />
            <q-toggle v-model="form.is_superuser" label="Administrateur (accès au back-office)" />
            <q-toggle v-model="form.send_invitation" label="Envoyer l'invitation maintenant" />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Créer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Modification -->
    <q-dialog v-model="editDialog">
      <q-card style="min-width: 420px">
        <q-card-section class="text-h6">Modifier {{ editing?.email }}</q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-pt-none q-gutter-sm">
            <q-banner v-if="dialogError" class="bg-red-1 text-red-9" dense rounded>{{
              dialogError
            }}</q-banner>
            <q-input v-model="editForm.full_name" label="Nom complet" outlined dense />
            <q-input v-model="editForm.phone" label="Téléphone" outlined dense />
            <q-select
              v-model="editForm.price_group_id"
              :options="groupChoices"
              label="Groupe de prix"
              outlined
              dense
              emit-value
              map-options
              clearable
            />
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat label="Annuler" v-close-popup />
            <q-btn type="submit" color="primary" label="Enregistrer" :loading="saving" />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { createUser, listUsers, resendInvitation, updateUser, type AdminUser } from '@/api/users';
import { listPriceGroups, type PriceGroup } from '@/api/eligibility';
import { extractApiError } from '@/api/errors';

const PAGE_SIZE = 50;

const rows = ref<AdminUser[]>([]);
const count = ref(0);
const page = ref(1);
const loading = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const groups = ref<PriceGroup[]>([]);

const search = ref<string | null>(null);
const groupFilter = ref<string | null>(null);
type StatusFilter = 'all' | 'pending' | 'opened' | 'inactive';
const statusFilter = ref<StatusFilter>('all');

const statusOptions = [
  { label: 'Tous', value: 'all' },
  { label: 'Invitation en attente', value: 'pending' },
  { label: 'Comptes ouverts', value: 'opened' },
  { label: 'Désactivés', value: 'inactive' },
];
const groupOptions = computed(() => [
  { label: 'Tous les groupes', value: null },
  ...groups.value.map((g) => ({ label: g.label, value: g.id })),
]);
const groupChoices = computed(() =>
  groups.value.map((g) => ({ label: `${g.label} (${g.code})`, value: g.id })),
);
const totalPages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)));

const req = [(v: string | null | undefined) => (!!v && v.length > 0) || 'Requis'];

const columns: QTableColumn[] = [
  { name: 'identity', label: 'Compte', field: 'email', align: 'left' },
  { name: 'group', label: 'Groupe', field: 'price_group_label', align: 'left' },
  { name: 'status', label: 'Statut', field: 'is_active', align: 'left' },
  { name: 'last_login', label: 'Dernière connexion', field: 'last_login', align: 'left' },
  { name: 'created_at', label: 'Créé le', field: 'created_at', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
];

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
}

function statusOf(user: AdminUser): { label: string; color: string } {
  if (!user.is_active) return { label: 'Désactivé', color: 'grey-6' };
  if (user.locked_until && new Date(user.locked_until) > new Date()) {
    return { label: 'Verrouillé', color: 'orange' };
  }
  if (user.invitation_pending) {
    const expired =
      !user.invitation_expires_at || new Date(user.invitation_expires_at) < new Date();
    return expired
      ? { label: 'Invitation expirée', color: 'deep-orange' }
      : { label: 'Invitation en attente', color: 'blue' };
  }
  return { label: 'Actif', color: 'green' };
}

function onFilterChange() {
  page.value = 1;
  void load();
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    if (!groups.value.length) groups.value = await listPriceGroups();
    const result = await listUsers({
      q: search.value,
      price_group_id: groupFilter.value,
      is_active:
        statusFilter.value === 'inactive' ? false : statusFilter.value === 'all' ? null : true,
      invitation_pending:
        statusFilter.value === 'pending' ? true : statusFilter.value === 'opened' ? false : null,
      skip: (page.value - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
    rows.value = result.data;
    count.value = result.count;
  } catch (err) {
    error.value = extractApiError(err) ?? 'Chargement impossible.';
  } finally {
    loading.value = false;
  }
}

// Actions de ligne
const busyIds = ref(new Set<string>());

function withBusy(id: string, fn: () => Promise<void>): Promise<void> {
  busyIds.value = new Set(busyIds.value).add(id);
  return fn().finally(() => {
    const next = new Set(busyIds.value);
    next.delete(id);
    busyIds.value = next;
  });
}

async function onResend(user: AdminUser) {
  notice.value = null;
  error.value = null;
  await withBusy(user.id, async () => {
    try {
      const result = await resendInvitation(user.id);
      notice.value = result.email_sent
        ? `Invitation renvoyée à ${user.email}.`
        : `Invitation régénérée, mais l'email vers ${user.email} n'est pas parti (voir les logs).`;
      await load();
    } catch (err) {
      error.value = extractApiError(err) ?? 'Renvoi impossible.';
    }
  });
}

async function onToggleActive(user: AdminUser) {
  notice.value = null;
  error.value = null;
  await withBusy(user.id, async () => {
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      await load();
    } catch (err) {
      error.value = extractApiError(err) ?? 'Modification impossible.';
    }
  });
}

// Création
const createDialog = ref(false);
const saving = ref(false);
const dialogError = ref<string | null>(null);
const form = reactive({
  email: '',
  full_name: '',
  phone: '',
  price_group_id: null as string | null,
  is_superuser: false,
  send_invitation: true,
});

function openCreate() {
  dialogError.value = null;
  form.email = '';
  form.full_name = '';
  form.phone = '';
  form.price_group_id = null;
  form.is_superuser = false;
  form.send_invitation = true;
  createDialog.value = true;
}

async function submitCreate() {
  saving.value = true;
  dialogError.value = null;
  try {
    const result = await createUser({
      email: form.email.trim(),
      full_name: form.full_name.trim() || null,
      phone: form.phone.trim() || null,
      price_group_id: form.price_group_id,
      is_superuser: form.is_superuser,
      send_invitation: form.send_invitation,
    });
    createDialog.value = false;
    notice.value = !form.send_invitation
      ? `Compte ${result.user.email} créé sans invitation.`
      : result.email_sent
        ? `Compte créé, invitation envoyée à ${result.user.email}.`
        : `Compte ${result.user.email} créé, mais l'email d'invitation n'est pas parti — renvoyez-le depuis la liste.`;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Création impossible.';
  } finally {
    saving.value = false;
  }
}

// Modification
const editDialog = ref(false);
const editing = ref<AdminUser | null>(null);
const editForm = reactive({
  full_name: '',
  phone: '',
  price_group_id: null as string | null,
});

function openEdit(user: AdminUser) {
  dialogError.value = null;
  editing.value = user;
  editForm.full_name = user.full_name ?? '';
  editForm.phone = user.phone ?? '';
  editForm.price_group_id = user.price_group_id;
  editDialog.value = true;
}

async function submitEdit() {
  if (!editing.value) return;
  saving.value = true;
  dialogError.value = null;
  try {
    await updateUser(editing.value.id, {
      full_name: editForm.full_name.trim() || null,
      phone: editForm.phone.trim() || null,
      price_group_id: editForm.price_group_id,
    });
    editDialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? 'Enregistrement impossible.';
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
