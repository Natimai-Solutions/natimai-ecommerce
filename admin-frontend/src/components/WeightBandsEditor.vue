<template>
  <div class="q-gutter-y-sm">
    <h3 class="admin-subtitle q-mt-sm q-mb-none">{{ $t('logistics.bands') }}</h3>
    <div class="text-caption text-muted">{{ $t('logistics.bands_hint') }}</div>
    <div v-for="(band, index) in bands" :key="index" class="row items-start" style="gap: 8px">
      <q-input
        v-model="band.max_kg"
        :label="$t('logistics.up_to')"
        type="number"
        step="0.001"
        outlined
        dense
        bottom-slots
        class="col"
        :hint="band.max_kg.trim() ? undefined : $t('logistics.and_above')"
      />
      <q-input
        v-model="band.price"
        :label="$t('logistics.band_price', { currency })"
        type="number"
        step="0.01"
        outlined
        dense
        bottom-slots
        class="col"
      />
      <q-btn
        :aria-label="$t('logistics.remove_band')"
        flat
        dense
        round
        color="negative"
        icon="ph:trash"
        @click="bands.splice(index, 1)"
      >
        <q-tooltip>{{ $t('logistics.remove_band') }}</q-tooltip>
      </q-btn>
    </div>
    <q-btn
      flat
      dense
      no-caps
      icon="ph:plus"
      :label="$t('logistics.add_band')"
      @click="bands.push({ max_kg: '', price: '' })"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * Grille transporteur par tranches de poids, éditée en chaînes (q-input) ;
 * `bandsPayload` la sérialise pour l'API.
 */
import type { BandRow } from '@/utils/weightBands';

defineProps<{ currency: string }>();
const bands = defineModel<BandRow[]>({ required: true });
</script>
