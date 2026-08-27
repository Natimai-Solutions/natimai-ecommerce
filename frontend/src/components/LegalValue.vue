<!--
  Affiche une donnée d'identité légale, en signalant visuellement celles qui
  n'ont pas encore été renseignées.

  Un placeholder discret finit par se faire oublier et partir en production au
  milieu d'un paragraphe. En rouge et souligné, il ne passe pas inaperçu — même
  logique que le marqueur du PDF de facture.
-->
<template>
  <span v-if="missing" class="legal-value--missing" data-testid="legal-placeholder">{{
    value
  }}</span>
  <span v-else>{{ value }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { isLegalPlaceholder } from 'src/config/legalEntity';

const props = defineProps<{ value: string }>();

const missing = computed(() => isLegalPlaceholder(props.value));
</script>

<style scoped lang="scss">
.legal-value--missing {
  color: #b00020;
  font-weight: 600;
  text-decoration: underline wavy;
}
</style>
