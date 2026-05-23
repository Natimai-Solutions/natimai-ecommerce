<template>
  <q-page class="column items-center justify-center q-gutter-md q-pa-lg">
    <div class="text-h5 text-weight-bold">Bienvenue</div>
    <div class="text-body1 text-grey-7 text-center">
      Vous pouvez consulter le catalogue des produits.
    </div>
    <q-btn
      color="primary"
      label="Voir le catalogue"
      icon="storefront"
      :to="{ name: 'catalogue' }"
    />
  </q-page>
</template>
