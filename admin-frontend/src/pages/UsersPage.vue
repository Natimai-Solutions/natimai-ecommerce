<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('users.title')" :hint="$t('users.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:user-plus"
          :label="$t('users.create_account')"
          @click="openCreate"
        />
      </template>
    </PageHeader>

    <div class="admin-toolbar">
      <q-input
        v-model="search"
        :label="$t('users.search')"
        outlined
        dense
        clearable
        debounce="300"
        style="min-width: 280px"
        @update:model-value="onFilterChange"
      >
        <template #prepend><q-icon name="ph:magnifying-glass" /></template>
      </q-input>
      <q-select
        v-model="groupFilter"
        :options="groupOptions"
        :label="$t('users.price_group')"
        outlined
        dense
        emit-value
        map-options
        style="min-width: 220px"
        @update:model-value="onFilterChange"
      />
      <q-select
        v-model="statusFilter"
        :options="statusOptions"
        :label="$t('users.status')"
        outlined
        dense
        emit-value
        map-options
        style="min-width: 220px"
        @update:model-value="onFilterChange"
      />
    </div>

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

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
            <q-icon v-if="props.row.is_superuser" name="ph:shield-check" size="xs">
              <q-tooltip>{{ $t('users.admin') }}</q-tooltip>
            </q-icon>
            <q-icon
              v-if="props.row.is_superuser && props.row.totp_enabled"
              name="ph:device-mobile"
              size="xs"
              data-testid="user-2fa"
            >
              <q-tooltip>{{ $t('users.twofa') }}</q-tooltip>
            </q-icon>
          </div>
          <div class="text-caption text-muted">
            {{ [props.row.full_name, props.row.phone].filter(Boolean).join(' · ') || '—' }}
          </div>
        </q-td>
      </template>
      <template #body-cell-group="props">
        <q-td :props="props">{{ props.row.price_group_label ?? $t('users.default') }}</q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <StatusTag
            :label="statusOf(props.row).label"
            :tone="statusOf(props.row).tone"
            :icon="statusOf(props.row).icon"
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
          <q-btn flat round dense icon="ph:pencil-simple" @click="openEdit(props.row)">
            <q-tooltip>{{ $t('users.edit') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.invitation_pending && props.row.is_active"
            flat
            round
            dense
            icon="ph:paper-plane-tilt"
            :loading="busyIds.has(props.row.id)"
            @click="onResend(props.row)"
          >
            <q-tooltip>{{ $t('users.resend') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.is_superuser && props.row.totp_enabled"
            flat
            round
            dense
            icon="ph:shield-slash"
            :loading="busyIds.has(props.row.id)"
            @click="onResetTwoFactor(props.row)"
          >
            <q-tooltip>{{ $t('users.reset_2fa') }}</q-tooltip>
          </q-btn>
          <q-btn
            flat
            round
            dense
            :icon="props.row.is_active ? 'ph:user-minus' : 'ph:user-check'"
            :color="props.row.is_active ? 'negative' : undefined"
            :loading="busyIds.has(props.row.id)"
            @click="onToggleActive(props.row)"
          >
            <q-tooltip>{{
              props.row.is_active ? $t('users.disable') : $t('users.enable')
            }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{ loading ? $t('common.loading') : $t('users.none') }}</span>
      </template>
    </q-table>

    <div class="row items-center q-mt-md">
      <div class="text-caption text-muted col">{{ $t('users.count', { n: count }) }}</div>
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
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('users.create_title') }}</h2>
          <p class="app-dialog__text">
            {{ $t('users.create_hint') }}
          </p>
        </q-card-section>
        <q-form @submit.prevent="submitCreate">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input
              v-model="form.email"
              :label="$t('users.email')"
              type="email"
              outlined
              dense
              :rules="req"
            />
            <q-input v-model="form.full_name" :label="$t('users.full_name')" outlined dense />
            <q-input v-model="form.phone" :label="$t('users.phone')" outlined dense />
            <q-select
              v-model="form.price_group_id"
              :options="groupChoices"
              :label="$t('users.price_group')"
              outlined
              dense
              emit-value
              map-options
              clearable
            />
            <q-toggle v-model="form.is_superuser" :label="$t('users.is_admin')" />
            <q-toggle v-model="form.send_invitation" :label="$t('users.send_now')" />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('users.create')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>

    <!-- Modification -->
    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('users.edit_title', { email: editing?.email }) }}</h2>
        </q-card-section>
        <q-form @submit.prevent="submitEdit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-input v-model="editForm.full_name" :label="$t('users.full_name')" outlined dense />
            <q-input v-model="editForm.phone" :label="$t('users.phone')" outlined dense />
            <q-select
              v-model="editForm.price_group_id"
              :options="groupChoices"
              :label="$t('users.price_group')"
              outlined
              dense
              emit-value
              map-options
              clearable
            />
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" v-close-popup />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { intlLocale } from '@app/utils';
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';
import PageHeader from '@/components/PageHeader.vue';
import { createUser, listUsers, resendInvitation, updateUser, type AdminUser } from '@/api/users';
import { resetUserTwoFactor } from '@/api/security';
import { listPriceGroups, type PriceGroup } from '@/api/eligibility';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

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

const statusOptions = computed(() => [
  { label: t('users.opt_all'), value: 'all' },
  { label: t('users.st_pending'), value: 'pending' },
  { label: t('users.opt_opened'), value: 'opened' },
  { label: t('users.opt_disabled'), value: 'inactive' },
]);
const groupOptions = computed(() => [
  { label: t('users.all_groups'), value: null },
  ...groups.value.map((g) => ({ label: g.label, value: g.id })),
]);
const groupChoices = computed(() =>
  groups.value.map((g) => ({ label: `${g.label} (${g.code})`, value: g.id })),
);
const totalPages = computed(() => Math.max(1, Math.ceil(count.value / PAGE_SIZE)));

const req = [(v: string | null | undefined) => (!!v && v.length > 0) || t('common.required')];

const columns = computed<QTableColumn[]>(() => [
  { name: 'identity', label: t('users.col_account'), field: 'email', align: 'left' },
  { name: 'group', label: t('users.col_group'), field: 'price_group_label', align: 'left' },
  { name: 'status', label: t('users.col_status'), field: 'is_active', align: 'left' },
  { name: 'last_login', label: t('users.col_login'), field: 'last_login', align: 'left' },
  { name: 'created_at', label: t('users.col_created'), field: 'created_at', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

function formatDate(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(intlLocale(), { dateStyle: 'short', timeStyle: 'short' });
}

function statusOf(user: AdminUser): { label: string; tone: StatusTone; icon: string } {
  if (!user.is_active)
    return { label: t('users.st_disabled'), tone: 'neutral', icon: 'ph:minus-circle' };
  if (user.locked_until && new Date(user.locked_until) > new Date()) {
    return { label: t('users.st_locked'), tone: 'warn', icon: 'ph:lock' };
  }
  if (user.invitation_pending) {
    const expired =
      !user.invitation_expires_at || new Date(user.invitation_expires_at) < new Date();
    return expired
      ? { label: t('users.st_expired'), tone: 'warn', icon: 'ph:warning-circle' }
      : { label: t('users.st_pending'), tone: 'neutral', icon: 'ph:envelope-simple' };
  }
  return { label: t('users.st_active'), tone: 'ok', icon: 'ph:check-circle' };
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
    error.value = extractApiError(err) ?? t('common.load_failed');
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
        ? t('users.resent', { email: user.email })
        : t('users.resent_failed_mail', { email: user.email });
      await load();
    } catch (err) {
      error.value = extractApiError(err) ?? t('users.resend_failed');
    }
  });
}

async function onResetTwoFactor(user: AdminUser) {
  notice.value = null;
  error.value = null;
  await withBusy(user.id, async () => {
    try {
      await resetUserTwoFactor(user.id);
      notice.value = `${user.email} activera de nouveau la double authentification à sa prochaine connexion.`;
      await load();
    } catch (err) {
      error.value = extractApiError(err) ?? t('users.reset_failed');
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
      error.value = extractApiError(err) ?? t('users.edit_failed');
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
      ? t('users.created_no_invite', { email: result.user.email })
      : result.email_sent
        ? t('users.created_invited', { email: result.user.email })
        : t('users.created_mail_failed', { email: result.user.email });
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('users.create_failed');
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
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
