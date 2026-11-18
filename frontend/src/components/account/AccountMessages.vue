<template>
  <section class="app-section messages">
    <div class="app-section__head">
      <h2 class="app-section__title">{{ $t('messaging.title') }}</h2>
      <p v-if="availability" class="app-section__hint" data-testid="messaging-hours">
        {{ availability }}
      </p>
    </div>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <!-- New request -------------------------------------------------------->
    <q-form v-if="composing" class="messages__new" @submit.prevent="onCreate">
      <h3 class="messages__subtitle">{{ $t('messaging.new_title') }}</h3>
      <q-select
        v-model="draft.topic"
        :options="topicOptions"
        emit-value
        map-options
        outlined
        dense
        :label="$t('messaging.topic_label')"
        :rules="[(v: string) => !!v || $t('messaging.topic_rule')]"
        data-testid="messaging-topic"
      />
      <q-input
        v-model="draft.subject"
        outlined
        dense
        maxlength="200"
        :label="$t('messaging.subject_label')"
        data-testid="messaging-subject"
      />
      <q-input
        v-model="draft.body"
        type="textarea"
        autogrow
        outlined
        maxlength="4000"
        :label="$t('messaging.body_label')"
        :rules="[(v: string) => !!v.trim() || $t('messaging.body_rule')]"
        data-testid="messaging-body"
      />
      <p v-if="draft.context_type" class="messages__about">
        <q-icon name="ph:link" size="16px" /> {{ $t(`messaging.about.${draft.context_type}`) }}
      </p>
      <div class="row q-gutter-sm justify-end">
        <q-btn flat no-caps :label="$t('common.cancel')" @click="closeComposer" />
        <q-btn
          type="submit"
          unelevated
          no-caps
          color="primary"
          icon-right="ph:paper-plane-right"
          :label="$t('messaging.send')"
          :loading="sending"
          data-testid="messaging-create"
        />
      </div>
    </q-form>

    <!-- One conversation --------------------------------------------------->
    <div v-else-if="current" class="messages__thread" data-testid="messaging-thread">
      <div class="messages__thread-head">
        <q-btn
          flat
          dense
          no-caps
          icon="ph:arrow-left"
          :label="$t('messaging.back')"
          @click="closeThread"
        />
        <div class="messages__thread-title">
          <strong>{{ current.subject }}</strong>
          <span class="app-row__meta">
            <span class="font-mono">{{ current.number }}</span> ·
            {{ topicLabel(current.topic) }}
          </span>
        </div>
        <StatusTag :tone="statusTone(current.status)" :label="statusLabel(current.status)" />
      </div>

      <ol class="messages__list" aria-live="polite">
        <li
          v-for="message in current.messages"
          :key="message.id"
          class="message"
          :class="`message--${message.side}`"
        >
          <span class="message__meta">
            {{
              message.side === 'staff'
                ? message.author_name || $t('messaging.team')
                : $t('messaging.you')
            }}
            · {{ formatDateTime(message.created_at) }}
          </span>
          <p class="message__body">{{ message.body }}</p>
        </li>
      </ol>

      <q-form class="messages__reply" @submit.prevent="onReply">
        <q-input
          v-model="reply"
          type="textarea"
          autogrow
          outlined
          maxlength="4000"
          :label="
            current.status === 'resolved'
              ? $t('messaging.reopen_hint')
              : $t('messaging.reply_label')
          "
          data-testid="messaging-reply"
        />
        <div class="row q-gutter-sm justify-end">
          <q-btn
            v-if="current.status !== 'resolved'"
            flat
            no-caps
            icon="ph:check-circle"
            :label="$t('messaging.resolve')"
            :loading="resolving"
            data-testid="messaging-resolve"
            @click="onResolve"
          />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            icon-right="ph:paper-plane-right"
            :label="$t('messaging.send')"
            :disable="!reply.trim()"
            :loading="sending"
            data-testid="messaging-send"
          />
        </div>
      </q-form>
    </div>

    <!-- The list ----------------------------------------------------------->
    <template v-else>
      <div class="row justify-end q-mb-md">
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="ph:plus"
          :label="$t('messaging.new')"
          data-testid="messaging-new"
          @click="openComposer()"
        />
      </div>
      <ul v-if="loading" class="app-rows" aria-busy="true">
        <li v-for="n in 2" :key="n" class="app-row">
          <div class="app-row__main">
            <q-skeleton type="text" width="40%" />
            <q-skeleton type="text" width="60%" />
          </div>
        </li>
      </ul>
      <div v-else-if="!conversations.length" class="app-empty">
        <q-icon name="ph:chat-circle-text" size="36px" class="text-subtle" />
        <h3>{{ $t('messaging.none') }}</h3>
        <p>{{ $t('messaging.none_text') }}</p>
      </div>
      <ul v-else class="app-rows" data-testid="messaging-list">
        <li v-for="item in conversations" :key="item.id" class="app-row">
          <button type="button" class="messages__row" @click="openThread(item.id)">
            <span class="app-row__main">
              <span class="app-row__title">
                <span
                  v-if="item.unread"
                  class="messages__dot"
                  :aria-label="$t('messaging.unread')"
                />
                {{ item.subject }}
              </span>
              <span class="app-row__meta">
                <span class="font-mono">{{ item.number }}</span> · {{ topicLabel(item.topic) }}
                <template v-if="item.last_message_at">
                  · {{ formatDateTime(item.last_message_at) }}
                </template>
              </span>
            </span>
            <StatusTag :tone="statusTone(item.status)" :label="statusLabel(item.status)" />
          </button>
        </li>
      </ul>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { formatDateTime } from '@app/utils';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import type { StatusTone } from '@app/ui/statusTone';

import {
  getMyConversation,
  listMyConversations,
  markConversationRead,
  openConversation,
  postMyMessage,
  resolveMyConversation,
  type ConversationDetail,
  type ConversationSummary,
} from '@/api/messaging';
import { useMessagingStore } from '@/stores/messaging';
import { apiErrorMessage } from '@/utils/errors';

/** The open thread asks for new messages every five seconds. */
const THREAD_POLL_MS = 5_000;

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const messaging = useMessagingStore();

const conversations = ref<ConversationSummary[]>([]);
const current = ref<ConversationDetail | null>(null);
const loading = ref(true);
const sending = ref(false);
const resolving = ref(false);
const error = ref<string | null>(null);
const reply = ref('');
const composing = ref(false);
const draft = reactive({
  topic: '',
  subject: '',
  body: '',
  context_type: null as string | null,
  context_id: null as string | null,
});
let poll: ReturnType<typeof setInterval> | null = null;

const topicOptions = computed(() =>
  (messaging.info?.channels ?? []).flatMap((group) =>
    group.topics.map((topic) => ({
      label: `${t(`messaging.channel.${group.channel}`)} — ${topicLabel(topic)}`,
      value: topic,
    })),
  ),
);

/** « We answer Monday to Friday, 8:00–17:00 (Tahiti time), usually within 24 h. » */
const availability = computed(() => {
  const info = messaging.info;
  if (!info) return '';
  const days = info.days.join(',') === '1,2,3,4,5' ? t('messaging.weekdays') : daysLabel(info.days);
  const delay =
    info.response_time.unit === 'business_days'
      ? t('messaging.delay_days', info.response_time.value)
      : t('messaging.delay_hours', { n: info.response_time.value });
  return t('messaging.availability', {
    days,
    start: info.hours_start,
    end: info.hours_end,
    delay,
  });
});

function daysLabel(days: number[]): string {
  return days.map((d) => t(`messaging.day.${d}`)).join(', ');
}

function topicLabel(topic: string): string {
  return t(`messaging.topic.${topic}`);
}

function statusLabel(status: string): string {
  return t(`messaging.status.${status}`);
}

function statusTone(status: string): StatusTone {
  return status === 'pending' ? 'warn' : status === 'resolved' ? 'neutral' : 'ok';
}

async function loadList() {
  loading.value = true;
  try {
    conversations.value = await listMyConversations();
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('messaging.load_failed');
  } finally {
    loading.value = false;
  }
}

function stopPolling() {
  if (poll !== null) clearInterval(poll);
  poll = null;
}

async function pollThread() {
  const conversation = current.value;
  if (!conversation || document.visibilityState !== 'visible') return;
  const last = conversation.messages?.[conversation.messages.length - 1]?.created_at;
  try {
    const fresh = await getMyConversation(conversation.id, last ?? undefined);
    if (current.value?.id !== conversation.id) return;
    const known = new Set((current.value.messages ?? []).map((m) => m.id));
    const added = (fresh.messages ?? []).filter((m) => !known.has(m.id));
    current.value = {
      ...fresh,
      messages: [...(current.value.messages ?? []), ...added],
    };
    if (added.some((m) => m.side === 'staff')) await markRead(conversation.id);
  } catch {
    // The next tick tries again.
  }
}

async function markRead(id: string) {
  try {
    await markConversationRead(id);
    await messaging.refreshUnread();
  } catch {
    // Read markers are a convenience.
  }
}

async function showThread(id: string) {
  error.value = null;
  stopPolling();
  try {
    current.value = await getMyConversation(id);
    await markRead(id);
    poll = setInterval(() => void pollThread(), THREAD_POLL_MS);
  } catch (err) {
    current.value = null;
    error.value = apiErrorMessage(err) ?? t('messaging.load_failed');
  }
}

function openThread(id: string) {
  void router.replace({ query: { ...route.query, c: id, new: undefined } });
}

function closeThread() {
  void router.replace({ query: { ...route.query, c: undefined } });
}

function openComposer() {
  void router.replace({ query: { ...route.query, new: '1', c: undefined } });
}

function closeComposer() {
  void router.replace({
    query: {
      ...route.query,
      new: undefined,
      topic: undefined,
      context_type: undefined,
      context_id: undefined,
    },
  });
}

/** The query string drives the view: `c` (a conversation), `new` (the form,
 *  pre-filled by `topic`, `context_type`, `context_id` from a shortcut). */
async function syncWithRoute() {
  const id = typeof route.query.c === 'string' ? route.query.c : null;
  composing.value = !id && route.query.new === '1';
  if (composing.value) {
    stopPolling();
    current.value = null;
    draft.topic = typeof route.query.topic === 'string' ? route.query.topic : '';
    draft.context_type =
      typeof route.query.context_type === 'string' ? route.query.context_type : null;
    draft.context_id = typeof route.query.context_id === 'string' ? route.query.context_id : null;
    return;
  }
  if (id) {
    if (current.value?.id !== id) await showThread(id);
    return;
  }
  stopPolling();
  current.value = null;
  await loadList();
}

async function onCreate() {
  if (!draft.topic || !draft.body.trim()) return;
  sending.value = true;
  error.value = null;
  try {
    const created = await openConversation({
      topic: draft.topic,
      subject: draft.subject.trim(),
      body: draft.body,
      context_type: draft.context_type,
      context_id: draft.context_id,
    });
    draft.subject = '';
    draft.body = '';
    void router.replace({
      query: {
        tab: 'messages',
        c: created.id,
      },
    });
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('messaging.send_failed');
  } finally {
    sending.value = false;
  }
}

async function onReply() {
  const conversation = current.value;
  if (!conversation || !reply.value.trim()) return;
  sending.value = true;
  error.value = null;
  try {
    current.value = await postMyMessage(conversation.id, reply.value);
    reply.value = '';
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('messaging.send_failed');
  } finally {
    sending.value = false;
  }
}

async function onResolve() {
  const conversation = current.value;
  if (!conversation) return;
  resolving.value = true;
  try {
    const summary = await resolveMyConversation(conversation.id);
    current.value = { ...conversation, status: summary.status };
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('messaging.send_failed');
  } finally {
    resolving.value = false;
  }
}

watch(
  () => [route.query.c, route.query.new],
  () => void syncWithRoute(),
);
onMounted(async () => {
  await messaging.loadInfo();
  await syncWithRoute();
});
onBeforeUnmount(stopPolling);
</script>

<style scoped lang="scss">
.messages__new,
.messages__reply {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.messages__subtitle {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

.messages__about {
  margin: 0;
  font-size: 13px;
  color: var(--n-ink-3);
  display: flex;
  align-items: center;
  gap: 6px;
}

.messages__row {
  all: unset;
  box-sizing: border-box;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;

  &:focus-visible {
    outline: 2px solid var(--n-accent);
    outline-offset: 2px;
    border-radius: var(--n-radius);
  }
}

.messages__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: var(--n-accent);
  vertical-align: middle;
}

.messages__thread-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;

  @media (max-width: 599px) {
    flex-direction: column;
    align-items: flex-start;
  }
}

.messages__thread-title {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.messages__list {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message {
  max-width: min(560px, 88%);
  padding: 10px 14px;
  border-radius: var(--n-radius);
  border: 1px solid var(--n-line);

  &--customer {
    align-self: flex-end;
    background: var(--n-accent-soft);
  }

  &--staff {
    align-self: flex-start;
    background: var(--n-tile);
  }
}

.message__meta {
  display: block;
  font-size: 12px;
  color: var(--n-ink-3);
  margin-bottom: 4px;
}

.message__body {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
