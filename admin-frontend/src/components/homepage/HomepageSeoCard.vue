<template>
  <section class="homepage-seo" data-testid="homepage-seo">
    <h2 class="admin-subtitle">{{ $t('homepage.seo_title') }}</h2>
    <p class="admin-hint">{{ $t('homepage.seo_hint') }}</p>
    <AppNotice v-if="error" tone="error" dense class="q-mb-sm">{{ error }}</AppNotice>
    <AppNotice v-if="saved" tone="success" dense class="q-mb-sm">{{
      $t('homepage.seo_saved')
    }}</AppNotice>
    <q-form class="q-gutter-sm" @submit.prevent="save">
      <template v-for="lang in locales" :key="lang">
        <h3 v-if="locales.length > 1" class="homepage-seo__lang">{{ lang.toUpperCase() }}</h3>
        <q-input
          v-model="texts[lang]!.title"
          outlined
          dense
          counter
          maxlength="70"
          :label="$t('homepage.seo_meta_title')"
          :data-testid="`seo-title-${lang}`"
        />
        <q-input
          v-model="texts[lang]!.description"
          type="textarea"
          autogrow
          outlined
          dense
          counter
          maxlength="170"
          :label="$t('homepage.seo_meta_description')"
        />
      </template>
      <div class="row justify-end">
        <q-btn
          type="submit"
          color="primary"
          unelevated
          no-caps
          :label="$t('common.save')"
          :loading="saving"
          data-testid="seo-save"
        />
      </div>
    </q-form>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import AppNotice from '@app/ui/AppNotice.vue';

import { extractApiError } from '@/api/errors';
import { getHomepageSeo, saveHomepageSeo } from '@/api/homepage';
import { useShopConfigStore } from '@/stores/shopConfig';

const { t } = useI18n();
const shop = useShopConfigStore();
/** The shop's language first: its texts are the source of the others. */
const locales = computed<string[]>(() => shop.config?.available_locales ?? ['fr', 'en']);
const texts = reactive<Record<string, { title: string; description: string }>>({});
const saving = ref(false);
const saved = ref(false);
const error = ref<string | null>(null);

function ensure(lang: string) {
  texts[lang] ??= { title: '', description: '' };
  return texts[lang];
}
// Every language has its fields before the first render (the shop's
// languages may arrive after this card).
watch(locales, (codes) => codes.forEach(ensure), { immediate: true });

async function load() {
  for (const lang of locales.value) ensure(lang);
  try {
    const seo = await getHomepageSeo();
    const [source, ...others] = locales.value;
    if (source) Object.assign(ensure(source), { title: seo.title, description: seo.description });
    for (const lang of others) {
      const entry = (seo.translations ?? {})[lang] ?? {};
      Object.assign(ensure(lang), {
        title: typeof entry['title'] === 'string' ? entry['title'] : '',
        description: typeof entry['description'] === 'string' ? entry['description'] : '',
      });
    }
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  }
}

async function save() {
  saving.value = true;
  saved.value = false;
  error.value = null;
  const [source, ...others] = locales.value;
  try {
    await saveHomepageSeo({
      title: source ? ensure(source).title.trim() : '',
      description: source ? ensure(source).description.trim() : '',
      translations: Object.fromEntries(
        others.map((lang) => [
          lang,
          { title: ensure(lang).title.trim(), description: ensure(lang).description.trim() },
        ]),
      ),
    });
    saved.value = true;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.save_failed');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped lang="scss">
.homepage-seo {
  margin-top: 32px;
  max-width: 720px;
}

.homepage-seo__lang {
  margin: 12px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--n-ink-2);
}
</style>
