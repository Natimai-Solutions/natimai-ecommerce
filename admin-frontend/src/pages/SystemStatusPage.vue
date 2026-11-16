<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('system_status.title')" :hint="$t('system_status.hint')">
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

    <template v-if="status">
      <AppNotice
        :tone="status.level === 'ok' ? 'success' : status.level === 'warn' ? 'warning' : 'error'"
        class="q-mb-md"
        data-testid="system-status-level"
      >
        {{ $t(`system_status.level_${status.level}`) }}
      </AppNotice>

      <div class="status-grid">
        <section class="app-panel">
          <h2 class="admin-subtitle">{{ $t('system_status.outbox') }}</h2>
          <StatusTag
            :tone="tone(status.outbox_level)"
            :label="$t(`system_status.${status.outbox_level}`)"
          />
          <dl class="admin-dl">
            <dt>{{ $t('system_status.outbox_pending') }}</dt>
            <dd class="font-mono">{{ status.outbox_pending }}</dd>
            <dt>{{ $t('system_status.outbox_oldest') }}</dt>
            <dd class="font-mono">
              {{
                status.outbox_oldest_pending_minutes === null
                  ? '—'
                  : $t('system_status.minutes', { n: status.outbox_oldest_pending_minutes })
              }}
            </dd>
            <dt>{{ $t('system_status.outbox_failed') }}</dt>
            <dd class="font-mono">{{ status.outbox_failed }}</dd>
          </dl>
        </section>

        <section class="app-panel">
          <h2 class="admin-subtitle">{{ $t('system_status.emails') }}</h2>
          <StatusTag
            :tone="tone(status.email_level)"
            :label="$t(`system_status.${status.email_level}`)"
          />
          <dl class="admin-dl">
            <dt>{{ $t('system_status.emails_failed') }}</dt>
            <dd class="font-mono">{{ status.emails_failed_24h }}</dd>
            <dt>{{ $t('system_status.emails_stuck') }}</dt>
            <dd class="font-mono">{{ status.emails_queued_stuck }}</dd>
            <dt>{{ $t('system_status.email_provider') }}</dt>
            <dd>
              {{
                status.email_provider_configured ? $t('system_status.configured') : $t('system_status.missing')
              }}
            </dd>
            <dt>{{ $t('system_status.alert_webhook') }}</dt>
            <dd>
              {{ status.alert_webhook_configured ? $t('system_status.configured') : $t('system_status.missing') }}
            </dd>
          </dl>
        </section>

        <section class="app-panel">
          <h2 class="admin-subtitle">{{ $t('system_status.rates') }}</h2>
          <p v-if="!status.currency_rates.length" class="text-subtle">
            {{ $t('system_status.no_rates') }}
          </p>
          <ul v-else class="status-list">
            <li v-for="rate in status.currency_rates" :key="rate.currency">
              <span class="font-mono">{{ rate.currency }}</span>
              <StatusTag
                :tone="tone(rate.level)"
                :label="$t('system_status.rate_age', { n: rate.age_days })"
              />
            </li>
          </ul>
        </section>
      </div>

      <h2 class="admin-subtitle q-mt-lg">{{ $t('system_status.tasks') }}</h2>
      <q-table
        :rows="status.tasks"
        :columns="columns"
        row-key="name"
        flat
        bordered
        :pagination="{ rowsPerPage: 0 }"
        hide-pagination
        :no-data-label="$t('system_status.no_tasks')"
      >
        <template #body-cell-level="props">
          <q-td :props="props">
            <StatusTag
              :tone="tone(props.row.level)"
              :label="$t(`system_status.task_${props.row.last_status ?? 'running'}`)"
            />
          </q-td>
        </template>
        <template #body-cell-error="props">
          <q-td :props="props" class="status-error">{{ props.row.last_error ?? '' }}</q-td>
        </template>
      </q-table>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QTableColumn } from 'quasar';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';
import { formatDateTime } from '@app/utils';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { getSystemStatus, type SystemStatus, type TaskRun } from '@/api/systemStatus';

/**
 * « État du système » (functional audit, November 2026): a stopped task, an
 * outbox backlog or an e-mail provider down were learnt from a customer.
 */
const { t } = useI18n();
const status = ref<SystemStatus | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

function tone(level: string): StatusTone {
  return level === 'ok' ? 'ok' : level === 'warn' ? 'warn' : 'danger';
}

const columns = computed<QTableColumn<TaskRun>[]>(() => [
  { name: 'name', label: t('system_status.col_task'), field: 'name', align: 'left' },
  { name: 'level', label: t('system_status.col_status'), field: 'level', align: 'left' },
  {
    name: 'success',
    label: t('system_status.col_success'),
    field: (row) => formatDateTime(row.last_success_at),
    align: 'left',
  },
  {
    name: 'failure',
    label: t('system_status.col_failure'),
    field: (row) => formatDateTime(row.last_failure_at),
    align: 'left',
  },
  { name: 'error', label: t('system_status.col_error'), field: 'last_error', align: 'left' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    status.value = await getSystemStatus();
  } catch (err) {
    error.value = extractApiError(err) ?? t('system_status.load_failed');
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.status-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.status-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: grid;
  gap: 6px;

  li {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}

.status-error {
  max-width: 420px;
  white-space: normal;
  color: var(--n-ink-2);
}
</style>
