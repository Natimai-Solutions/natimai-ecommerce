<template>
  <q-page class="admin-page messaging">
    <PageHeader :title="$t('messaging.title')">
      <template #actions>
        <q-btn
          flat
          no-caps
          icon="ph:arrow-clockwise"
          :label="$t('common.refresh')"
          :loading="loading"
          @click="refreshAll"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" dense class="q-mb-md">{{ error }}</AppNotice>

    <div class="messaging__layout" :class="{ 'messaging__layout--detail': !!selectedId }">
      <!-- Queue ---------------------------------------------------------->
      <section class="messaging__queue" :aria-label="$t('messaging.queue')">
        <q-tabs v-model="tab" dense no-caps align="left" class="messaging__tabs" outside-arrows>
          <q-tab v-for="item in tabs" :key="item.value" :name="item.value">
            <span>
              {{ item.label }}
              <q-badge v-if="item.count" rounded color="primary" class="q-ml-xs">
                {{ item.count }}
              </q-badge>
            </span>
          </q-tab>
        </q-tabs>
        <div class="row q-col-gutter-sm q-my-sm">
          <q-select
            v-model="channel"
            class="col-12 col-sm-5"
            :options="channelOptions"
            emit-value
            map-options
            clearable
            outlined
            dense
            :label="$t('messaging.channel_label')"
          />
          <q-input
            v-model="search"
            class="col-12 col-sm-7"
            outlined
            dense
            clearable
            debounce="300"
            :label="$t('messaging.search')"
          >
            <template #prepend><q-icon name="ph:magnifying-glass" /></template>
          </q-input>
        </div>

        <div v-if="loading && !page.data.length" class="q-pa-md">
          <q-skeleton v-for="n in 4" :key="n" type="text" class="q-mb-sm" />
        </div>
        <div v-else-if="!page.data.length" class="app-empty">
          <q-icon name="ph:chat-circle-text" size="28px" class="text-subtle" />
          <h3>{{ $t('messaging.empty') }}</h3>
        </div>
        <q-list v-else bordered separator class="rounded-borders">
          <q-item
            v-for="item in page.data"
            :key="item.id"
            clickable
            :active="item.id === selectedId"
            active-class="messaging__item--active"
            data-testid="conversation-row"
            @click="select(item.id)"
          >
            <q-item-section>
              <q-item-label class="text-weight-medium">
                <span v-if="item.staff_unread" class="messaging__dot" />
                {{ item.subject }}
              </q-item-label>
              <q-item-label caption>
                <span class="font-mono">{{ item.number }}</span> ·
                {{ item.customer_name || item.customer_email }}
              </q-item-label>
              <q-item-label caption>
                {{ channelLabel(item.channel) }} — {{ topicLabel(item.topic) }}
                <template v-if="item.assigned_to_name"> · {{ item.assigned_to_name }}</template>
              </q-item-label>
            </q-item-section>
            <q-item-section side top>
              <q-item-label caption>
                {{ item.last_message_at ? formatDateTime(item.last_message_at) : '' }}
              </q-item-label>
              <StatusTag :tone="statusTone(item.status)" :label="statusLabel(item.status)" />
            </q-item-section>
          </q-item>
        </q-list>
        <div v-if="page.count > PAGE_SIZE" class="row justify-center q-mt-sm">
          <q-pagination
            v-model="pageNumber"
            :max="Math.ceil(page.count / PAGE_SIZE)"
            direction-links
            boundary-links
            :max-pages="6"
          />
        </div>
      </section>

      <!-- Conversation ----------------------------------------------------->
      <section v-if="current" class="messaging__detail" data-testid="conversation-detail">
        <div class="messaging__detail-head">
          <q-btn
            class="lt-md"
            flat
            dense
            no-caps
            icon="ph:arrow-left"
            :label="$t('messaging.back')"
            @click="select(null)"
          />
          <div class="col">
            <h2 class="app-section__title q-my-none">{{ current.subject }}</h2>
            <p class="admin-hint q-my-none">
              <span class="font-mono">{{ current.number }}</span> ·
              {{ current.customer_name }}
              <template v-if="current.customer_email">
                &lt;{{ current.customer_email }}&gt;</template
              >
              <template v-if="current.context_label">
                · {{ $t(`messaging.context.${current.context_type}`) }} {{ current.context_label }}
              </template>
            </p>
          </div>
          <StatusTag :tone="statusTone(current.status)" :label="statusLabel(current.status)" />
        </div>

        <div class="row q-col-gutter-sm items-center q-mb-sm">
          <q-select
            :model-value="current.topic"
            class="col-12 col-sm-6"
            :options="topicOptions"
            emit-value
            map-options
            outlined
            dense
            :label="$t('messaging.topic_label')"
            @update:model-value="onMove"
          />
          <div class="col-12 col-sm-6 row q-gutter-xs justify-end">
            <q-chip v-if="current.assigned_to_name" icon="ph:user" dense>
              {{ current.assigned_to_name }}
            </q-chip>
            <q-btn
              v-if="current.assigned_to_id !== meId"
              outline
              dense
              no-caps
              :label="$t('messaging.claim')"
              data-testid="conversation-claim"
              @click="act('claim')"
            />
            <q-btn
              v-if="current.assigned_to_id"
              flat
              dense
              no-caps
              :label="$t('messaging.release')"
              @click="act('release')"
            />
            <q-btn-dropdown flat dense no-caps :label="$t('messaging.transfer')">
              <q-list dense>
                <q-item
                  v-for="member in team"
                  :key="member.id"
                  v-close-popup
                  clickable
                  @click="onTransfer(member.id)"
                >
                  <q-item-section>{{ member.name }}</q-item-section>
                </q-item>
              </q-list>
            </q-btn-dropdown>
            <q-btn
              v-if="current.status !== 'resolved'"
              unelevated
              dense
              no-caps
              color="primary"
              icon="ph:check-circle"
              :label="$t('messaging.resolve')"
              data-testid="conversation-resolve"
              @click="act('resolve')"
            />
          </div>
        </div>

        <ol class="messaging__thread" aria-live="polite">
          <li
            v-for="message in current.messages"
            :key="message.id"
            :class="[
              'msg',
              `msg--${message.kind}`,
              message.kind === 'message' ? `msg--${message.side}` : '',
            ]"
          >
            <template v-if="message.kind === 'event'">
              {{ eventLabel(message) }} · {{ formatDateTime(message.created_at) }}
            </template>
            <template v-else>
              <span class="msg__meta">
                <template v-if="message.kind === 'note'">{{ $t('messaging.note') }} · </template>
                {{
                  message.side === 'customer'
                    ? current.customer_name || $t('messaging.customer')
                    : message.author_name
                }}
                · {{ formatDateTime(message.created_at) }}
              </span>
              <p v-if="message.body" class="msg__body">{{ message.body }}</p>
              <div v-if="message.attachments?.length" class="msg__files">
                <q-btn
                  v-for="file in message.attachments"
                  :key="file.id"
                  flat
                  dense
                  no-caps
                  size="sm"
                  :icon="file.mime === 'application/pdf' ? 'ph:file-pdf' : 'ph:image'"
                  :label="file.filename"
                  @click="onDownloadFile(file.id, file.filename)"
                />
              </div>
            </template>
          </li>
        </ol>

        <q-form class="messaging__composer" @submit.prevent="onSend">
          <q-btn-toggle
            v-model="composeKind"
            no-caps
            dense
            unelevated
            toggle-color="primary"
            :options="[
              { label: $t('messaging.reply'), value: 'message' },
              { label: $t('messaging.note'), value: 'note' },
            ]"
          />
          <q-input
            v-model="draft"
            type="textarea"
            autogrow
            outlined
            maxlength="4000"
            :label="composeKind === 'note' ? $t('messaging.note_hint') : $t('messaging.reply_hint')"
            data-testid="conversation-draft"
          />
          <q-chip
            v-if="pendingFile"
            removable
            icon="ph:paperclip"
            class="self-start"
            @remove="pendingFile = null"
          >
            {{ pendingFile.name }}
          </q-chip>
          <input
            ref="fileInput"
            type="file"
            class="hidden"
            accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
            @change="onPickFile"
          />
          <div class="row justify-end q-gutter-sm">
            <q-btn
              flat
              no-caps
              icon="ph:paperclip"
              :label="$t('messaging.attach')"
              @click="fileInput?.click()"
            />
            <q-btn
              type="submit"
              unelevated
              no-caps
              :color="composeKind === 'note' ? 'warning' : 'primary'"
              icon-right="ph:paper-plane-right"
              :label="composeKind === 'note' ? $t('messaging.add_note') : $t('messaging.send')"
              :disable="!draft.trim() && !pendingFile"
              :loading="sending"
              data-testid="conversation-send"
            />
          </div>
        </q-form>
      </section>
      <section v-else class="messaging__detail messaging__detail--empty gt-sm">
        <div class="app-empty">
          <q-icon name="ph:chat-circle-text" size="28px" class="text-subtle" />
          <h3>{{ $t('messaging.pick') }}</h3>
        </div>
      </section>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { formatDateTime } from '@app/utils';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';

import PageHeader from '@/components/PageHeader.vue';
import { useConfirm } from '@/composables/useConfirm';
import { extractApiError } from '@/api/errors';
import { getMe } from '@/api/me';
import {
  CHANNEL_TOPICS,
  conversationAction,
  conversationTeam,
  downloadStaffFile,
  postStaffFile,
  getConversation,
  listConversations,
  moveConversation,
  postStaffMessage,
  readConversation,
  transferConversation,
  type ConversationPage,
  type ConversationTab,
  type StaffConversationDetail,
  type TeamMember,
} from '@/api/messaging';
import { useMessagingStore } from '@/stores/messaging';

const PAGE_SIZE = 50;
const THREAD_POLL_MS = 5_000;
const QUEUE_POLL_MS = 30_000;

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const { ask } = useConfirm();
const counters = useMessagingStore();

const tab = ref<ConversationTab>('todo');
const channel = ref<string | null>(null);
const search = ref<string | null>(null);
const pageNumber = ref(1);
const page = ref<ConversationPage>({ data: [], count: 0 });
const loading = ref(false);
const error = ref<string | null>(null);
const current = ref<StaffConversationDetail | null>(null);
const team = ref<TeamMember[]>([]);
const meId = ref<string | null>(null);
const draft = ref('');
const composeKind = ref<'message' | 'note'>('message');
const sending = ref(false);
let threadTimer: ReturnType<typeof setInterval> | null = null;
let queueTimer: ReturnType<typeof setInterval> | null = null;

const selectedId = computed(() =>
  typeof route.params.id === 'string' && route.params.id ? route.params.id : null,
);

const tabs = computed(() => [
  { value: 'todo' as const, label: t('messaging.tab_todo'), count: counters.summary.todo },
  { value: 'mine' as const, label: t('messaging.tab_mine'), count: counters.summary.mine },
  { value: 'pending' as const, label: t('messaging.tab_pending'), count: 0 },
  { value: 'resolved' as const, label: t('messaging.tab_resolved'), count: 0 },
  { value: 'all' as const, label: t('messaging.tab_all'), count: 0 },
]);

const channelOptions = computed(() =>
  Object.keys(CHANNEL_TOPICS).map((key) => ({ label: channelLabel(key), value: key })),
);
const topicOptions = computed(() =>
  Object.entries(CHANNEL_TOPICS).flatMap(([key, topics]) =>
    topics.map((topic) => ({
      label: `${channelLabel(key)} — ${topicLabel(topic)}`,
      value: topic,
      channel: key,
    })),
  ),
);

function channelLabel(key: string): string {
  return t(`messaging.channel.${key}`);
}
function topicLabel(key: string): string {
  return t(`messaging.topic.${key}`);
}
function statusLabel(status: string): string {
  return t(`messaging.status.${status}`);
}
function statusTone(status: string): StatusTone {
  return status === 'open' ? 'warn' : status === 'pending' ? 'ok' : 'neutral';
}
function eventLabel(message: StaffConversationDetail['messages'][number]): string {
  const data = (message.data ?? {}) as Record<string, string>;
  return t(`messaging.event.${data['action'] ?? message.body}`, {
    by: data['by'] ?? '',
    to: data['to'] ?? '',
    topic: data['topic'] ? topicLabel(data['topic']) : '',
    days: data['days'] ?? '',
  });
}

async function loadQueue() {
  loading.value = true;
  try {
    page.value = await listConversations({
      tab: tab.value,
      channel: channel.value,
      q: search.value,
      skip: (pageNumber.value - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    });
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function stopThread() {
  if (threadTimer !== null) clearInterval(threadTimer);
  threadTimer = null;
}

async function pollThread() {
  const conversation = current.value;
  if (!conversation || document.visibilityState !== 'visible') return;
  const last = conversation.messages?.[conversation.messages.length - 1]?.created_at;
  try {
    const fresh = await getConversation(conversation.id, last ?? undefined);
    if (current.value?.id !== conversation.id) return;
    const known = new Set((current.value.messages ?? []).map((m) => m.id));
    const added = (fresh.messages ?? []).filter((m) => !known.has(m.id));
    current.value = { ...fresh, messages: [...(current.value.messages ?? []), ...added] };
    if (added.some((m) => m.side === 'customer' && m.kind === 'message')) {
      await readConversation(conversation.id);
    }
  } catch {
    // Next tick.
  }
}

async function openThread(id: string | null) {
  stopThread();
  error.value = null;
  if (!id) {
    current.value = null;
    return;
  }
  try {
    current.value = await getConversation(id);
    await readConversation(id);
    void counters.refresh();
    threadTimer = setInterval(() => void pollThread(), THREAD_POLL_MS);
  } catch (err) {
    current.value = null;
    error.value = extractApiError(err) ?? t('common.load_failed');
  }
}

function select(id: string | null) {
  void router.push(id ? `/messages/${id}` : '/messages');
}

function isConflict(err: unknown): boolean {
  const code = (err as { response?: { data?: { error?: { code?: string } } } })?.response?.data
    ?.error?.code;
  return code === 'messaging.already_claimed' || code === 'messaging.held_by_other';
}

/** An action on a conversation someone else holds asks before forcing. */
async function withForce(run: (force: boolean) => Promise<StaffConversationDetail>): Promise<void> {
  error.value = null;
  try {
    current.value = await run(false);
  } catch (err) {
    if (isConflict(err) && (await ask({ title: extractApiError(err) ?? '', destructive: false }))) {
      try {
        current.value = await run(true);
      } catch (again) {
        error.value = extractApiError(again) ?? t('common.save_failed');
      }
    } else if (!isConflict(err)) {
      error.value = extractApiError(err) ?? t('common.save_failed');
    }
  }
  void loadQueue();
  void counters.refresh();
}

function act(action: 'claim' | 'release' | 'resolve') {
  const id = current.value?.id;
  if (id) void withForce((force) => conversationAction(id, action, force));
}

function onTransfer(userId: string) {
  const id = current.value?.id;
  if (id) void withForce((force) => transferConversation(id, userId, force));
}

async function onMove(topic: string) {
  const conversation = current.value;
  const option = topicOptions.value.find((o) => o.value === topic);
  if (!conversation || !option) return;
  try {
    current.value = await moveConversation(conversation.id, option.channel, topic);
    void loadQueue();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  }
}

const fileInput = ref<HTMLInputElement | null>(null);
const pendingFile = ref<File | null>(null);

function onPickFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  input.value = '';
  if (file && file.size > 5 * 1024 * 1024) {
    error.value = t('messaging.file_too_large', { mb: 5 });
    return;
  }
  pendingFile.value = file;
}

async function onDownloadFile(attachmentId: string, filename: string) {
  const conversation = current.value;
  if (!conversation) return;
  try {
    await downloadStaffFile(conversation.id, attachmentId, filename);
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  }
}

async function onSend() {
  const conversation = current.value;
  if (!conversation || (!draft.value.trim() && !pendingFile.value)) return;
  sending.value = true;
  error.value = null;
  try {
    current.value = pendingFile.value
      ? await postStaffFile(conversation.id, pendingFile.value, draft.value, composeKind.value)
      : await postStaffMessage(conversation.id, draft.value, composeKind.value);
    pendingFile.value = null;
    draft.value = '';
    composeKind.value = 'message';
    void loadQueue();
    void counters.refresh();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    sending.value = false;
  }
}

async function refreshAll() {
  await Promise.all([loadQueue(), counters.refresh()]);
  if (selectedId.value) await openThread(selectedId.value);
}

watch([tab, channel, search], () => {
  pageNumber.value = 1;
  void loadQueue();
});
watch(pageNumber, () => void loadQueue());
watch(selectedId, (id) => void openThread(id));

onMounted(async () => {
  void loadQueue();
  void counters.refresh();
  conversationTeam()
    .then((members) => (team.value = members))
    .catch(() => (team.value = []));
  getMe()
    .then((me) => (meId.value = me.id))
    .catch(() => (meId.value = null));
  await openThread(selectedId.value);
  queueTimer = setInterval(() => {
    if (document.visibilityState === 'visible') void loadQueue();
  }, QUEUE_POLL_MS);
});

onBeforeUnmount(() => {
  stopThread();
  if (queueTimer !== null) clearInterval(queueTimer);
});
</script>

<style scoped lang="scss">
.messaging__layout {
  display: grid;
  grid-template-columns: minmax(320px, 420px) 1fr;
  gap: 24px;
  align-items: start;

  @media (max-width: 1023px) {
    grid-template-columns: 1fr;

    &--detail .messaging__queue {
      display: none;
    }
  }
}

.messaging__tabs {
  border-bottom: 1px solid var(--n-line);
}

.messaging__item--active {
  background: var(--n-tile);
}

.messaging__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--n-accent);
  vertical-align: middle;
}

.messaging__detail {
  min-width: 0;
}

.messaging__detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.messaging__thread {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg {
  max-width: min(640px, 92%);
  padding: 10px 14px;
  border-radius: var(--n-radius);
  border: 1px solid var(--n-line);

  &--customer {
    align-self: flex-start;
    background: var(--n-tile);
  }

  &--staff {
    align-self: flex-end;
    background: var(--n-accent-soft);
  }

  &--note {
    align-self: stretch;
    max-width: none;
    border-style: dashed;
    border-color: var(--n-warn);
  }

  &--event {
    align-self: center;
    border: none;
    padding: 0;
    font-size: 12px;
    color: var(--n-ink-3);
  }
}

.msg__meta {
  display: block;
  font-size: 12px;
  color: var(--n-ink-3);
  margin-bottom: 4px;
}

.msg__files {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.msg__body {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.messaging__composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
