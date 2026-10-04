<template>
  <q-page class="admin-page">
    <PageHeader :title="$t('languages.title')" :hint="$t('languages.hint')">
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

    <div v-if="error || notice" class="admin-notices">
      <AppNotice v-if="error" tone="error" dense>{{ error }}</AppNotice>
      <AppNotice v-if="notice" tone="success" dense>{{ notice }}</AppNotice>
    </div>

    <div v-if="loading && !loaded" class="text-center q-pa-xl"><q-spinner size="2.5em" /></div>

    <template v-else>
      <q-table
        flat
        bordered
        :rows="rows"
        :columns="columns"
        row-key="code"
        hide-pagination
        :rows-per-page-options="[0]"
        data-testid="languages-table"
      >
        <template #body-cell-language="props">
          <q-td :props="props">
            <div class="text-weight-medium">{{ props.row.label }}</div>
            <div class="text-subtle font-mono">{{ props.row.code }}</div>
          </q-td>
        </template>
        <template #body-cell-offered="props">
          <q-td :props="props">
            <q-toggle
              :model-value="props.row.offered"
              :disable="busy || props.row.isDefault"
              :aria-label="$t('languages.offered')"
              :data-testid="`language-offered-${props.row.code}`"
              @update:model-value="(on: boolean) => setOffered(props.row.code, on)"
            />
            <StatusTag
              :label="props.row.offered ? $t('languages.on') : $t('languages.off')"
              :tone="props.row.offered ? 'ok' : 'neutral'"
            />
          </q-td>
        </template>
        <template #body-cell-default="props">
          <q-td :props="props">
            <q-radio
              :model-value="defaultLocale"
              :val="props.row.code"
              :disable="busy"
              :aria-label="$t('languages.default')"
              :data-testid="`language-default-${props.row.code}`"
              @update:model-value="(code: string) => setDefault(code)"
            />
          </q-td>
        </template>
      </q-table>

      <AppNotice tone="info" dense class="q-mt-md">{{ $t('languages.add_hint') }}</AppNotice>
      <p class="admin-hint q-mt-sm q-mb-none">
        {{ $t('languages.settings_link') }}
        <router-link to="/system-settings">{{ $t('layout.nav.settings') }}</router-link>
      </p>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { QTableColumn } from 'quasar';
import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import PageHeader from '@/components/PageHeader.vue';
import { extractApiError } from '@/api/errors';
import { listSystemSettings, updateSystemSetting } from '@/api/systemSettings';
import { useShopConfigStore } from '@/stores/shopConfig';

/**
 * Languages of the storefront: one line per language shipped with the
 * interface, a switch to offer it to the visitor and the default language.
 * Both are the `shop_locales` / `shop_default_locale` settings (Parameters →
 * Display): this screen only makes them easier to find.
 */
const { t } = useI18n();
const shopConfig = useShopConfigStore();

const OFFERED_KEY = 'shop_locales';
const DEFAULT_KEY = 'shop_default_locale';

const LABELS: Record<string, string> = { fr: 'Français', en: 'English' };

const loading = ref(false);
const loaded = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const supported = ref<string[]>([]);
const offered = ref<string[]>([]);
const defaultLocale = ref<string>('fr');

const columns = computed<QTableColumn[]>(() => [
  { name: 'language', label: t('languages.language'), field: 'label', align: 'left' },
  { name: 'offered', label: t('languages.offered'), field: 'offered', align: 'left' },
  { name: 'default', label: t('languages.default'), field: 'isDefault', align: 'left' },
]);

const rows = computed(() =>
  supported.value.map((code) => ({
    code,
    label: LABELS[code] ?? code.toUpperCase(),
    offered: offered.value.includes(code) || code === defaultLocale.value,
    isDefault: code === defaultLocale.value,
  })),
);

function splitList(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const settings = await listSystemSettings();
    const offeredSetting = settings.find((s) => s.key === OFFERED_KEY);
    const defaultSetting = settings.find((s) => s.key === DEFAULT_KEY);
    supported.value = offeredSetting?.choices ?? ['fr', 'en'];
    offered.value = splitList(offeredSetting?.value ?? '');
    defaultLocale.value = (defaultSetting?.value ?? '').trim() || supported.value[0] || 'fr';
    loaded.value = true;
  } catch (err) {
    error.value = extractApiError(err) ?? t('common.load_failed');
  } finally {
    loading.value = false;
  }
}

async function persist(nextOffered: string[], nextDefault: string) {
  busy.value = true;
  error.value = null;
  notice.value = null;
  try {
    // The default language is always offered: keep the stored list consistent.
    const ordered = supported.value.filter(
      (code) => nextOffered.includes(code) || code === nextDefault,
    );
    if (nextDefault !== defaultLocale.value) {
      await updateSystemSetting(DEFAULT_KEY, { value: nextDefault });
      defaultLocale.value = nextDefault;
    }
    await updateSystemSetting(OFFERED_KEY, { value: ordered.join(', ') });
    offered.value = ordered;
    notice.value = t('languages.saved');
    void shopConfig.reload();
  } catch (err) {
    error.value = extractApiError(err) ?? t('languages.save_failed');
  } finally {
    busy.value = false;
  }
}

function setOffered(code: string, on: boolean) {
  const next = on ? [...offered.value, code] : offered.value.filter((c) => c !== code);
  void persist(next, defaultLocale.value);
}

function setDefault(code: string) {
  void persist(offered.value, code);
}

onMounted(load);
</script>
