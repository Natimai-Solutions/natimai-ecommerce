<template>
  <section class="app-section">
    <div class="app-section__head">
      <h2 class="app-section__title">{{ $t('addresses.title') }}</h2>
      <p class="app-section__hint">
        {{ $t('addresses.hint') }}
      </p>
      <q-btn
        unelevated
        color="primary"
        icon="ph:plus"
        :label="$t('addresses.add')"
        class="app-section__action"
        @click="openAddressDialog()"
      />
    </div>

    <AppNotice v-if="addressesError" tone="error" class="q-mb-md">
      {{ addressesError }}
    </AppNotice>

    <div v-if="loadingAddresses" class="address-grid" aria-busy="true">
      <q-skeleton v-for="n in 2" :key="n" height="148px" class="address-card__skeleton" />
    </div>

    <div v-else-if="addresses.length === 0" class="app-empty">
      <q-icon name="ph:map-pin" size="36px" class="text-subtle" />
      <h3>{{ $t('addresses.none') }}</h3>
      <p>{{ $t('addresses.none_text') }}</p>
    </div>

    <ul v-else class="address-grid">
      <li v-for="address in addresses" :key="address.id" class="address-card">
        <div class="address-card__head">
          <span class="address-card__type">{{ typeLabel(address.type) }}</span>
          <StatusTag
            :tone="address.is_validated ? 'ok' : 'neutral'"
            :icon="address.is_validated ? 'ph:seal-check' : 'ph:clock'"
            :label="address.is_validated ? $t('addresses.verified') : $t('addresses.verifying')"
          />
        </div>
        <address class="address-card__body">
          {{ address.street }}<br />
          {{ address.postal_code }} {{ address.city }}<br />
          <template v-if="address.state">{{ address.state }}<br /></template>
          {{ countryLabel(address.country) }}
        </address>
        <div class="address-card__actions">
          <button type="button" class="text-link" @click="openAddressDialog(address)">
            {{ $t('addresses.edit') }}
          </button>
          <button type="button" class="text-link" @click="confirmDelete(address)">
            {{ $t('addresses.delete') }}
          </button>
        </div>
      </li>
    </ul>

    <AddressDialog v-model="addressDialog" :address="editing" @saved="loadAddresses" />

    <!-- ========================== Delete confirmation ========================== -->
    <q-dialog v-model="deleteDialog">
      <q-card class="app-dialog app-dialog--narrow">
        <q-card-section class="app-dialog__head">
          <h2 class="app-dialog__title">{{ $t('addresses.delete_title') }}</h2>
          <p class="app-dialog__text">{{ $t('addresses.delete_text') }}</p>
        </q-card-section>
        <q-card-actions align="right" class="app-dialog__actions">
          <q-btn flat :label="$t('addresses.cancel')" v-close-popup />
          <q-btn
            flat
            :label="$t('addresses.delete_btn')"
            color="negative"
            :loading="deleting"
            @click="performDelete"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { countryLabel } from '@app/utils';

import AppNotice from '@app/ui/AppNotice.vue';
import StatusTag from '@app/ui/StatusTag.vue';
import AddressDialog from '@/components/AddressDialog.vue';
import { deleteMyAddress, listMyAddresses, type Address } from '@/api/addresses';
import { apiErrorMessage } from '@/utils/errors';

const { t } = useI18n();

const addressTypeOptions = computed(() => [
  { label: t('addresses.type.shipping'), value: 'shipping' },
  { label: t('addresses.type.billing'), value: 'billing' },
  { label: t('addresses.type.other'), value: 'other' },
]);

function typeLabel(type: string): string {
  return addressTypeOptions.value.find((o) => o.value === type)?.label ?? type;
}

const loadingAddresses = ref(true);
const addressesError = ref<string | null>(null);
const addresses = ref<Address[]>([]);

const deleteDialog = ref(false);
const deleting = ref(false);
const addressToDelete = ref<Address | null>(null);

const addressDialog = ref(false);
const editing = ref<Address | null>(null);

function openAddressDialog(address?: Address) {
  editing.value = address ?? null;
  addressDialog.value = true;
}

async function loadAddresses() {
  loadingAddresses.value = true;
  addressesError.value = null;
  try {
    addresses.value = await listMyAddresses();
  } catch (err) {
    addressesError.value = apiErrorMessage(err) ?? t('addresses.load_failed');
  } finally {
    loadingAddresses.value = false;
  }
}

function confirmDelete(address: Address) {
  addressToDelete.value = address;
  deleteDialog.value = true;
}

async function performDelete() {
  if (!addressToDelete.value) return;
  deleting.value = true;
  try {
    await deleteMyAddress(addressToDelete.value.id);
    deleteDialog.value = false;
    addressToDelete.value = null;
    await loadAddresses();
  } catch (err) {
    addressesError.value = apiErrorMessage(err) ?? t('addresses.delete_failed');
    deleteDialog.value = false;
  } finally {
    deleting.value = false;
  }
}

onMounted(loadAddresses);
</script>

<style scoped lang="scss">
.address-grid {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.address-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid var(--n-line);
  border-radius: 8px;
  background: var(--n-surface);
}

.address-card__skeleton {
  border-radius: 8px;
}

.address-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.address-card__type {
  font-size: 13px;
  font-weight: 500;
  color: var(--n-ink-2);
}

.address-card__body {
  flex-grow: 1;
  font-style: normal;
  font-size: 14px;
  line-height: 1.55;
}

.address-card__actions {
  display: flex;
  gap: 16px;
}
</style>
