<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('canned.title')" :hint="$t('canned.hint')">
      <template #actions>
        <q-btn
          color="primary"
          unelevated
          no-caps
          icon="ph:plus"
          :label="$t('canned.new')"
          data-testid="canned-new"
          @click="openEdit(null)"
        />
      </template>
    </PageHeader>

    <AppNotice v-if="error" tone="error" class="q-mb-md">{{ error }}</AppNotice>

    <div v-if="loading && !replies.length" class="q-pa-md">
      <q-skeleton v-for="n in 3" :key="n" type="text" class="q-mb-sm" />
    </div>
    <div v-else-if="!replies.length" class="app-empty">
      <q-icon name="ph:chat-text" size="28px" class="text-subtle" />
      <h3>{{ $t('canned.empty') }}</h3>
    </div>
    <q-list v-else bordered separator class="rounded-borders">
      <q-item v-for="reply in replies" :key="reply.id" data-testid="canned-row">
        <q-item-section>
          <q-item-label class="text-weight-medium">{{ reply.title }}</q-item-label>
          <q-item-label caption lines="2">{{ reply.body }}</q-item-label>
          <q-item-label caption>
            {{
              reply.channel ? $t(`messaging.channel.${reply.channel}`) : $t('canned.all_channels')
            }}
            <template v-if="Object.keys(reply.translations ?? {}).length">
              ·
              {{
                Object.keys(reply.translations ?? {})
                  .join(', ')
                  .toUpperCase()
              }}
            </template>
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div class="row no-wrap">
            <q-btn
              flat
              round
              dense
              icon="ph:pencil-simple"
              :aria-label="$t('common.edit')"
              @click="openEdit(reply)"
            />
            <q-btn
              flat
              round
              dense
              icon="ph:trash"
              color="negative"
              :aria-label="$t('common.delete')"
              @click="remove(reply)"
            />
          </div>
        </q-item-section>
      </q-item>
    </q-list>

    <q-dialog v-model="dialog">
      <q-card class="app-dialog app-dialog--wide">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">
            {{ editingId ? $t('canned.edit_title') : $t('canned.new') }}
          </h2>
        </q-card-section>
        <q-form @submit.prevent="submit">
          <q-card-section class="q-gutter-sm">
            <AppNotice v-if="dialogError" tone="error" dense>{{ dialogError }}</AppNotice>
            <q-select
              v-model="form.channel"
              :options="channelOptions"
              emit-value
              map-options
              clearable
              outlined
              dense
              :label="$t('canned.channel')"
              :hint="$t('canned.channel_hint')"
            />
            <q-input
              v-model="form.title"
              outlined
              dense
              maxlength="120"
              :label="$t('canned.field_title')"
              :rules="[(v: string) => !!v.trim() || $t('canned.required')]"
              data-testid="canned-title"
            />
            <q-input
              v-model="form.body"
              type="textarea"
              autogrow
              outlined
              maxlength="4000"
              :label="$t('canned.body')"
              :hint="$t('canned.variables')"
              :rules="[(v: string) => !!v.trim() || $t('canned.required')]"
              data-testid="canned-body"
            />
            <template v-for="lang in otherLocales" :key="lang">
              <h3 class="admin-subtitle q-mt-md">{{ lang.toUpperCase() }}</h3>
              <q-input
                v-model="form.translations[lang]!.title"
                outlined
                dense
                maxlength="120"
                :label="$t('canned.field_title')"
              />
              <q-input
                v-model="form.translations[lang]!.body"
                type="textarea"
                autogrow
                outlined
                maxlength="4000"
                :label="$t('canned.body')"
              />
            </template>
          </q-card-section>
          <q-card-actions align="right" class="app-dialog__actions">
            <q-btn flat no-caps :label="$t('common.cancel')" @click="dialog = false" />
            <q-btn
              type="submit"
              color="primary"
              unelevated
              no-caps
              :label="$t('common.save')"
              :loading="saving"
              data-testid="canned-save"
            />
          </q-card-actions>
        </q-form>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';

import PageHeader from '@/components/PageHeader.vue';
import { useConfirm } from '@/composables/useConfirm';
import { extractApiError } from '@/api/errors';
import {
  CHANNEL_TOPICS,
  deleteCannedReply,
  listCannedReplies,
  saveCannedReply,
  type CannedReply,
} from '@/api/messaging';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();
const { confirmDelete } = useConfirm();
const shop = useShopConfigStore();

const replies = ref<CannedReply[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const dialog = ref(false);
const dialogError = ref<string | null>(null);
const saving = ref(false);
const editingId = ref<string | null>(null);

/** The languages offered besides the shop's own (the source text). */
const otherLocales = computed(() => (shop.config?.available_locales ?? ['fr', 'en']).slice(1));
const channelOptions = computed(() =>
  Object.keys(CHANNEL_TOPICS).map((key) => ({ label: t(`messaging.channel.${key}`), value: key })),
);

interface CannedForm {
  channel: string | null;
  title: string;
  body: string;
  translations: Record<string, { title: string; body: string }>;
}

const form = reactive<CannedForm>({ channel: null, title: '', body: '', translations: {} });

async function load() {
  loading.value = true;
  error.value = null;
  try {
    replies.value = await listCannedReplies();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

function openEdit(reply: CannedReply | null) {
  editingId.value = reply?.id ?? null;
  dialogError.value = null;
  form.channel = reply?.channel ?? null;
  form.title = reply?.title ?? '';
  form.body = reply?.body ?? '';
  form.translations = {};
  for (const lang of otherLocales.value) {
    const texts = (reply?.translations ?? {})[lang] ?? {};
    form.translations[lang] = { title: texts['title'] ?? '', body: texts['body'] ?? '' };
  }
  dialog.value = true;
}

async function submit() {
  saving.value = true;
  dialogError.value = null;
  try {
    await saveCannedReply(
      {
        channel: form.channel,
        title: form.title.trim(),
        body: form.body,
        translations: form.translations,
      },
      editingId.value ?? undefined,
    );
    dialog.value = false;
    await load();
  } catch (err) {
    dialogError.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

async function remove(reply: CannedReply) {
  if (!(await confirmDelete(reply.title))) return;
  try {
    await deleteCannedReply(reply.id);
    await load();
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.delete_failed');
  }
}

onMounted(load);
</script>
