<template>
  <q-page class="quote-confirmation q-pa-md">
    <div class="quote-confirmation__content">
      <q-card flat bordered class="quote-confirmation__card q-pa-xl">
        <q-icon name="check_circle" size="72px" color="positive" class="q-mb-md" />

        <h1 class="text-h4 text-weight-bold q-my-none q-mb-sm">Demande envoyée</h1>

        <p class="text-body1 text-grey-8 q-mb-lg">
          Votre panier a bien été transmis à notre équipe. Nous revenons vers vous rapidement avec
          votre devis.
        </p>

        <p v-if="customerEmail" class="text-body2 text-grey-7 q-mb-lg">
          Confirmation enregistrée pour: {{ customerEmail }}
        </p>

        <div class="row q-col-gutter-sm justify-center">
          <div class="col-12 col-sm-auto">
            <q-btn
              unelevated
              color="primary"
              icon="storefront"
              label="Retour au catalogue"
              class="full-width"
              :to="{ name: 'catalogue' }"
            />
          </div>
        </div>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

const customerEmail = computed(() => {
  const value = route.query.email;
  if (typeof value !== 'string') return '';

  const normalized = value.trim().toLowerCase();
  return /^(?:[^\s@]+)@(?:[^\s@]+)\.[^\s@]+$/.test(normalized) ? normalized : '';
});
</script>

<style scoped lang="scss">
.quote-confirmation {
  min-height: calc(100vh - 120px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.quote-confirmation__content {
  width: min(760px, 100%);
}

.quote-confirmation__card {
  text-align: center;
  border-radius: 20px;
  background: linear-gradient(180deg, #f6fff8 0%, #ffffff 70%);
}
</style>
