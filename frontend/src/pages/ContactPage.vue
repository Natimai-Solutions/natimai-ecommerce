<template>
  <q-page class="contact page-container">
    <header class="contact__head">
      <h1 class="contact__title">{{ $t('contact.title') }}</h1>
      <p class="contact__lead">{{ $t('contact.lead') }}</p>
      <p v-if="availability" class="contact__hours" data-testid="contact-hours">
        <q-icon name="ph:clock" size="18px" /> {{ availability }}
      </p>
      <p v-if="messaging.info?.contact_email" class="contact__hours">
        <q-icon name="ph:envelope-simple" size="18px" />
        <a :href="`mailto:${messaging.info.contact_email}`">{{ messaging.info.contact_email }}</a>
      </p>
    </header>

    <!-- Signed in: the messages of the account keep the history. -->
    <AppNotice v-if="authStore.isAuthenticated" tone="info" class="contact__card">
      {{ $t('contact.signed_in') }}
      <template #action>
        <q-btn
          unelevated
          no-caps
          color="primary"
          :label="$t('contact.to_messages')"
          :to="{ name: 'account', query: { tab: 'messages', new: '1' } }"
        />
      </template>
    </AppNotice>

    <AppNotice
      v-else-if="sent"
      tone="success"
      icon="ph:check-circle"
      class="contact__card"
      data-testid="contact-sent"
    >
      {{ $t('contact.sent') }}
    </AppNotice>

    <q-form v-else class="contact__form contact__card" @submit.prevent="onSubmit">
      <AppNotice v-if="error" tone="error">{{ error }}</AppNotice>
      <q-select
        v-model="form.topic"
        :options="topicOptions"
        emit-value
        map-options
        outlined
        :label="$t('contact.topic')"
        :rules="[(v: string) => !!v || $t('contact.topic_rule')]"
        data-testid="contact-topic"
      />
      <div class="row q-col-gutter-sm">
        <q-input
          v-model="form.name"
          class="col-12 col-sm-6"
          outlined
          maxlength="255"
          autocomplete="name"
          :label="$t('contact.name')"
          :rules="[(v: string) => !!v.trim() || $t('contact.name_rule')]"
          data-testid="contact-name"
        />
        <q-input
          v-model="form.email"
          class="col-12 col-sm-6"
          type="email"
          outlined
          maxlength="255"
          autocomplete="email"
          :label="$t('contact.email')"
          :rules="[(v: string) => /.+@.+\..+/.test(v) || $t('contact.email_rule')]"
          data-testid="contact-email"
        />
        <q-input
          v-model="form.phone"
          class="col-12 col-sm-6"
          outlined
          maxlength="50"
          autocomplete="tel"
          :label="$t('contact.phone')"
        />
        <q-input
          v-model="form.company"
          class="col-12 col-sm-6"
          outlined
          maxlength="255"
          autocomplete="organization"
          :label="$t('contact.company')"
        />
      </div>
      <q-input v-model="form.subject" outlined maxlength="200" :label="$t('contact.subject')" />
      <q-input
        v-model="form.body"
        type="textarea"
        autogrow
        outlined
        maxlength="4000"
        :label="$t('contact.body')"
        :rules="[(v: string) => !!v.trim() || $t('contact.body_rule')]"
        data-testid="contact-body"
      />
      <!-- Honeypot: hidden from people, filled by robots. -->
      <div class="contact__trap" aria-hidden="true">
        <label>
          Website
          <input
            v-model="form.website"
            type="text"
            name="website"
            tabindex="-1"
            autocomplete="off"
          />
        </label>
      </div>
      <div v-if="captcha.enabled.value" ref="captchaEl" />
      <p class="contact__privacy">{{ $t('contact.privacy') }}</p>
      <div class="row justify-end">
        <q-btn
          type="submit"
          unelevated
          no-caps
          color="primary"
          icon-right="ph:paper-plane-right"
          :label="$t('contact.send')"
          :loading="sending"
          :disable="sending || (captcha.enabled.value && !captcha.ready.value)"
          data-testid="contact-send"
        />
      </div>
    </q-form>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';

import { sendContact } from '@/api/messaging';
import { usePageMeta } from '@/composables/usePageMeta';
import { useTurnstile } from '@/composables/useTurnstile';
import { useAuthStore } from '@/stores/auth';
import { useMessagingStore } from '@/stores/messaging';
import { apiErrorMessage } from '@/utils/errors';

const { t, locale } = useI18n();
const authStore = useAuthStore();
const messaging = useMessagingStore();
const captcha = useTurnstile();
const captchaEl = ref<HTMLElement | null>(null);
watch(captchaEl, (el) => void captcha.mount(el, locale.value));

usePageMeta(() => ({ title: t('contact.title'), description: t('contact.lead') }));

const form = reactive({
  topic: '',
  name: '',
  email: '',
  phone: '',
  company: '',
  subject: '',
  body: '',
  website: '',
});
const sending = ref(false);
const sent = ref(false);
const error = ref<string | null>(null);

const topicOptions = computed(() =>
  (messaging.info?.channels ?? []).flatMap((group) =>
    group.topics.map((topic) => ({
      label: `${t(`messaging.channel.${group.channel}`)} — ${t(`messaging.topic.${topic}`)}`,
      value: topic,
    })),
  ),
);

const availability = computed(() => {
  const info = messaging.info;
  if (!info) return '';
  const days =
    info.days.join(',') === '1,2,3,4,5'
      ? t('messaging.weekdays')
      : info.days.map((d) => t(`messaging.day.${d}`)).join(', ');
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

async function onSubmit() {
  sending.value = true;
  error.value = null;
  try {
    await sendContact(
      {
        topic: form.topic,
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        company: form.company.trim() || null,
        subject: form.subject.trim(),
        body: form.body,
        website: form.website,
      },
      captcha.headers(),
    );
    sent.value = true;
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('contact.failed');
  } finally {
    sending.value = false;
    captcha.reset();
  }
}

onMounted(() => void messaging.loadInfo());
</script>

<style scoped lang="scss">
.contact {
  padding-top: 48px;
  padding-bottom: 96px;
  max-width: 760px;
}

.contact__title {
  margin: 0 0 8px;
  font-weight: 600;
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.1;
}

.contact__lead {
  margin: 0 0 12px;
  color: var(--n-ink-2);
  font-size: 17px;
}

.contact__hours {
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--n-ink-2);
}

.contact__card {
  margin-top: 28px;
}

.contact__form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contact__trap {
  position: absolute;
  left: -10000px;
  width: 1px;
  height: 1px;
  overflow: hidden;
}

.contact__privacy {
  margin: 0;
  font-size: 13px;
  color: var(--n-ink-3);
}
</style>
