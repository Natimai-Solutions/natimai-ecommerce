<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('audit.title')" :hint="$t('audit.hint')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="load"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div class="row q-mb-md" style="gap: 8px">
      <q-select
        v-model="event"
        :options="eventOptions"
        :label="$t('audit.type')"
        outlined
        dense
        emit-value
        map-options
        clearable
        style="min-width: 220px"
        @update:model-value="reload"
      />
      <q-input
        v-model="pathContains"
        :label="$t('audit.path_contains')"
        outlined
        dense
        clearable
        debounce="400"
        style="min-width: 240px"
        @update:model-value="reload"
      />
    </div>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      :pagination="pagination"
      :rows-number="count"
      :rows-per-page-options="[50]"
      @request="onRequest"
    >
      <template #body-cell-event="props">
        <q-td :props="props">
          <StatusTag :label="eventLabel(props.row)" :tone="eventTone(props.row)" />
        </q-td>
      </template>
      <template #body-cell-action="props">
        <q-td :props="props" class="audit__action">
          <span v-if="props.row.method" class="font-mono">{{ props.row.method }}</span>
          <span class="font-mono text-subtle q-ml-xs">{{
            props.row.route ?? props.row.path ?? ''
          }}</span>
          <div v-if="props.row.details" class="text-caption text-subtle font-mono">
            {{ summarize(props.row.details) }}
          </div>
        </q-td>
      </template>
      <template #no-data>
        <div class="full-width text-center text-subtle q-pa-md">{{ $t('audit.none') }}</div>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { intlLocale } from '@app/utils';
import { useI18n } from 'vue-i18n';
import { computed, onMounted, ref } from 'vue';
import type { QTableColumn, QTableProps } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { listAuditEntries, type AuditEntry } from '@/api/security';

const { t } = useI18n();

const PAGE_SIZE = 50;
const rows = ref<AuditEntry[]>([]);
const count = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const event = ref<string | null>(null);
const pathContains = ref<string | null>(null);
const pagination = ref({ page: 1, rowsPerPage: PAGE_SIZE, rowsNumber: 0 });

const EVENT_LABELS: Record<string, string> = {
  http: 'audit.ev.http',
  'auth.login.success': 'audit.ev.login_success',
  'auth.login.failed': 'audit.ev.login_failed',
  'auth.login.totp_failed': 'audit.ev.totp_failed',
  'auth.2fa.enabled': 'audit.ev.2fa_on',
  'auth.2fa.disabled': 'audit.ev.2fa_off',
  'auth.2fa.recovery_codes': 'audit.ev.recovery',
};
const eventOptions = computed(() => [
  { label: t('audit.opt.changes'), value: 'http' },
  { label: t('audit.opt.auth'), value: 'auth' },
  { label: t('audit.opt.failed'), value: 'auth.login.failed' },
]);

const columns = computed<QTableColumn[]>(() => [
  {
    name: 'created_at',
    label: t('audit.col_date'),
    field: 'created_at',
    align: 'left',
    format: (v: string) => new Date(v).toLocaleString(intlLocale()),
  },
  { name: 'actor', label: t('audit.col_admin'), field: 'actor_email', align: 'left' },
  { name: 'event', label: t('audit.col_type'), field: 'event', align: 'left' },
  { name: 'action', label: t('audit.col_action'), field: 'path', align: 'left' },
  { name: 'status', label: t('audit.col_result'), field: 'status_code', align: 'right' },
  { name: 'ip', label: t('audit.col_ip'), field: 'ip', align: 'left', classes: 'font-mono' },
]);

function eventLabel(row: AuditEntry): string {
  const key = EVENT_LABELS[row.event];
  return key ? t(key) : row.event;
}

function eventTone(row: AuditEntry): 'ok' | 'warn' | 'danger' | 'neutral' {
  if (row.event.endsWith('failed') || (row.status_code ?? 0) >= 400) return 'danger';
  if (row.event.startsWith('auth.2fa')) return 'warn';
  if (row.event === 'auth.login.success') return 'ok';
  return 'neutral';
}

function summarize(details: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [section, values] of Object.entries(details)) {
    if (values && typeof values === 'object') {
      for (const [k, v] of Object.entries(values as Record<string, unknown>)) {
        parts.push(`${k}=${String(v)}`);
      }
    } else {
      parts.push(`${section}=${String(values)}`);
    }
  }
  return parts.join(' · ');
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const page = await listAuditEntries({
      event: event.value,
      path_contains: pathContains.value,
      skip: (pagination.value.page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
    rows.value = page.data;
    count.value = page.count;
    pagination.value = { ...pagination.value, rowsNumber: page.count };
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function reload() {
  pagination.value = { ...pagination.value, page: 1 };
  void load();
}

function onRequest(props: Parameters<NonNullable<QTableProps['onRequest']>>[0]) {
  pagination.value = { ...pagination.value, page: props.pagination.page ?? 1 };
  void load();
}

onMounted(() => void load());
</script>

<style scoped>
.audit__action {
  white-space: normal;
  max-width: 520px;
}
</style>
