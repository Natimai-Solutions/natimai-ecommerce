<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
    <q-card class="app-dialog">
      <q-card-section class="app-dialog__head">
        <h2 class="app-dialog__title">{{ $t('quote_request.title') }}</h2>
        <p class="app-dialog__subtitle">{{ $t('quote_request.intro') }}</p>
      </q-card-section>
      <q-form @submit.prevent="submit">
        <q-card-section class="q-pt-none">
          <AppNotice v-if="error" dense tone="error" class="q-mb-md">{{ error }}</AppNotice>
          <template v-if="!authStore.isAuthenticated">
            <q-input
              v-model="email"
              type="email"
              :label="$t('quote_request.email')"
              outlined
              dense
              autocomplete="email"
              class="q-mb-sm"
              data-testid="quote-email"
              :rules="[
                (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || $t('quote_request.email_invalid'),
              ]"
            />
            <q-input
              v-model="name"
              :label="$t('quote_request.name')"
              outlined
              dense
              autocomplete="name"
              class="q-mb-sm"
            />
            <q-input
              v-model="phone"
              type="tel"
              :label="$t('quote_request.phone')"
              outlined
              dense
              autocomplete="tel"
              class="q-mb-sm"
            />
          </template>
          <q-input
            v-model="shippingAddress"
            :label="$t('quote_request.address')"
            outlined
            dense
            autogrow
            autocomplete="street-address"
            class="q-mb-sm"
          />
          <q-input
            v-model="notes"
            type="textarea"
            :label="$t('quote_request.notes')"
            :hint="$t('quote_request.notes_hint')"
            outlined
            dense
            autogrow
            maxlength="2000"
            data-testid="quote-notes"
          />
          <div v-if="!authStore.isAuthenticated && captcha.enabled.value" ref="captchaEl" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn v-close-popup flat no-caps :label="$t('common.cancel')" />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            :label="$t('quote_request.send')"
            :loading="sending"
            :disable="sending || (!authStore.isAuthenticated && !captcha.ready.value)"
            data-testid="quote-send"
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';

import AppNotice from '@app/ui/AppNotice.vue';
import { createQuoteRequest, replaceMyCartItems } from '@/api/cart';
import { useTurnstile } from '@/composables/useTurnstile';
import { useAuthStore } from '@/stores/auth';
import { useCartStore } from '@/stores/cart';
import { apiErrorMessage } from '@/utils/errors';

/**
 * « Demander un devis » from the cart. The request, its admin screen, the
 * PDF, the e-mail and « Commander ce devis » all existed; nothing in the
 * storefront let a customer ask for one (functional audit, November 2026).
 *
 * Signed in: the cart is sent as it is and the quote lands in « Mes devis ».
 * A visitor leaves an e-mail (and passes the captcha); the quote is e-mailed.
 */
defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [open: boolean] }>();

const { t, locale } = useI18n();
const router = useRouter();
const authStore = useAuthStore();
const cartStore = useCartStore();
const captcha = useTurnstile();
const captchaEl = ref<HTMLElement | null>(null);
watch(captchaEl, (el) => void captcha.mount(el, locale.value));

const email = ref('');
const name = ref('');
const phone = ref('');
const shippingAddress = ref('');
const notes = ref('');
const sending = ref(false);
const error = ref<string | null>(null);

async function submit() {
  sending.value = true;
  error.value = null;
  try {
    if (authStore.isAuthenticated) {
      // The quote is made from the account's server cart: send it first.
      await replaceMyCartItems({
        items: cartStore.items.map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          import_service_level: item.import_service_level ?? null,
        })),
      });
      await createQuoteRequest({
        shipping_address: shippingAddress.value.trim() || null,
        notes: notes.value.trim() || null,
      });
      emit('update:modelValue', false);
      await router.push({ name: 'cart-quote-confirmation' });
      return;
    }
    const sent = await cartStore.sendQuoteByEmail({
      customer_email: email.value,
      customer_name: name.value.trim() || null,
      customer_phone: phone.value.trim() || null,
      shipping_address: shippingAddress.value.trim() || null,
      notes: notes.value.trim() || null,
      headers: captcha.headers(),
    });
    captcha.reset(); // a Turnstile token is single-use
    if (!sent) {
      error.value = cartStore.error ?? t('quote_request.failed');
      return;
    }
    emit('update:modelValue', false);
    await router.push({
      name: 'cart-quote-confirmation',
      query: { email: email.value.trim().toLowerCase() },
    });
  } catch (err) {
    error.value = apiErrorMessage(err) ?? t('quote_request.failed');
  } finally {
    sending.value = false;
  }
}
</script>

<style scoped lang="scss">
.app-dialog__subtitle {
  margin: 6px 0 0;
  color: var(--n-ink-2);
  font-size: 14px;
}
</style>
