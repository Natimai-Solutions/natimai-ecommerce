<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('reviews.title')" :hint="$t('reviews.hint')">
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

    <div class="admin-toolbar">
      <q-btn-toggle
        v-model="status"
        no-caps
        unelevated
        toggle-color="primary"
        :options="statusOptions"
        data-testid="reviews-status"
        @update:model-value="load"
      />
      <span class="text-subtle text-caption">{{ $t('reviews.count', { n: count }, count) }}</span>
    </div>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      flat
      bordered
      dense
      :rows-per-page-options="[0]"
      hide-pagination
      data-testid="reviews-table"
    >
      <template #body-cell-author="props">
        <q-td :props="props">
          <div>{{ props.row.author_name || '—' }}</div>
          <div class="text-subtle text-caption">{{ props.row.author_email }}</div>
        </q-td>
      </template>
      <template #body-cell-rating="props">
        <q-td :props="props">
          <span class="review-stars" :aria-label="$t('reviews.rated', { n: props.row.rating })"
            >{{ '★'.repeat(props.row.rating)
            }}<span class="review-stars__off">{{ '★'.repeat(5 - props.row.rating) }}</span></span
          >
        </q-td>
      </template>
      <template #body-cell-comment="props">
        <q-td :props="props" class="review-comment">
          {{ props.row.comment || '—' }}
          <div v-if="props.row.verified_purchase" class="text-caption text-positive">
            <q-icon name="ph:seal-check" /> {{ $t('reviews.verified') }}
          </div>
          <div v-if="props.row.moderation_note" class="text-caption text-subtle">
            {{ $t('reviews.note') }} : {{ props.row.moderation_note }}
          </div>
        </q-td>
      </template>
      <template #body-cell-actions="props">
        <q-td :props="props" align="right" class="review-actions">
          <q-btn
            v-if="props.row.status !== 'approved'"
            flat
            round
            dense
            icon="ph:check"
            :aria-label="$t('reviews.approve')"
            :loading="savingId === props.row.id"
            data-testid="review-approve"
            @click="decide(props.row, 'approve')"
          >
            <q-tooltip>{{ $t('reviews.approve') }}</q-tooltip>
          </q-btn>
          <q-btn
            v-if="props.row.status !== 'rejected'"
            flat
            round
            dense
            color="negative"
            icon="ph:x"
            :aria-label="
              props.row.status === 'approved' ? $t('reviews.unpublish') : $t('reviews.reject')
            "
            data-testid="review-reject"
            @click="openReject(props.row)"
          >
            <q-tooltip>{{
              props.row.status === 'approved' ? $t('reviews.unpublish') : $t('reviews.reject')
            }}</q-tooltip>
          </q-btn>
        </q-td>
      </template>
      <template #no-data>
        <span class="text-subtle">{{ loading ? $t('common.loading') : $t('reviews.none') }}</span>
      </template>
    </q-table>

    <q-dialog v-model="rejectDialog">
      <q-card class="app-dialog">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('reviews.reject_title') }}</h2>
        </q-card-section>
        <q-card-section class="q-gutter-sm">
          <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
          <p class="text-caption text-muted">« {{ rejecting?.comment || '—' }} »</p>
          <q-input
            v-model="note"
            :label="$t('reviews.note_label')"
            outlined
            dense
            maxlength="300"
            type="textarea"
            autogrow
          />
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn v-close-popup flat no-caps :label="$t('common.cancel')" />
          <q-btn
            color="negative"
            unelevated
            no-caps
            :label="$t('reviews.reject')"
            :loading="savingId === rejecting?.id"
            data-testid="review-reject-confirm"
            @click="confirmReject"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QTableColumn } from 'quasar';
import { intlLocale } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import PageHeader from '@/components/PageHeader.vue';
import {
  listReviews,
  moderateReview,
  type ReviewStatus,
  type ReviewToModerate,
} from '@/api/reviews';
import { extractApiError } from '@/api/errors';

const { t } = useI18n();

const status = ref<ReviewStatus>('pending');
const rows = ref<ReviewToModerate[]>([]);
const count = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);
const savingId = ref<string | null>(null);

const statusOptions = computed(() => [
  { value: 'pending', label: t('reviews.st_pending') },
  { value: 'approved', label: t('reviews.st_approved') },
  { value: 'rejected', label: t('reviews.st_rejected') },
]);

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(intlLocale());
}

const columns = computed<QTableColumn<ReviewToModerate>[]>(() => [
  {
    name: 'created_at',
    label: t('reviews.col_date'),
    field: (row) => formatDate(row.modify_at ?? row.created_at),
    align: 'left',
  },
  {
    name: 'product',
    label: t('reviews.col_product'),
    field: (row) => row.product_name ?? '—',
    align: 'left',
  },
  { name: 'author', label: t('reviews.col_author'), field: 'author_name', align: 'left' },
  { name: 'rating', label: t('reviews.col_rating'), field: 'rating', align: 'left' },
  { name: 'comment', label: t('reviews.col_comment'), field: 'comment', align: 'left' },
  { name: 'actions', label: '', field: 'id', align: 'right' },
]);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const page = await listReviews(status.value);
    rows.value = page.data;
    count.value = page.count;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

async function decide(row: ReviewToModerate, decision: 'approve' | 'reject', reason?: string) {
  savingId.value = row.id;
  error.value = null;
  try {
    await moderateReview(row.id, decision, reason ?? null);
    await load();
    return true;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.action_failed');
    return false;
  } finally {
    savingId.value = null;
  }
}

const rejectDialog = ref(false);
const rejecting = ref<ReviewToModerate | null>(null);
const note = ref('');
const dialogError = ref<string | null>(null);

function openReject(row: ReviewToModerate) {
  rejecting.value = row;
  note.value = '';
  dialogError.value = null;
  rejectDialog.value = true;
}

async function confirmReject() {
  if (!rejecting.value) return;
  if (await decide(rejecting.value, 'reject', note.value.trim() || undefined)) {
    rejectDialog.value = false;
  } else {
    dialogError.value = error.value;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.review-stars {
  color: var(--n-warn);
  letter-spacing: 1px;
  white-space: nowrap;
}

.review-stars__off {
  color: var(--n-line-2);
}

.review-comment {
  min-width: 220px;
  max-width: 360px;
  white-space: normal;
}

.review-actions {
  white-space: nowrap;
}
</style>
