<!--
  Mentions légales — DOCUMENT À FAIRE VALIDER PAR UN CONSEIL JURIDIQUE avant
  mise en ligne. Compléter tous les champs [À COMPLÉTER : …] (grep-able).
-->
<template>
  <q-page class="legal-page q-pa-md">
    <div class="legal-page__content">
      <h1 class="text-h4 text-weight-bold q-mb-md">Mentions légales</h1>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Éditeur du site</h2>
      <p>
        Le présent site est édité par <strong>Natimai Solutions</strong>,
        [À COMPLÉTER : forme juridique] au capital de [À COMPLÉTER : capital social] XPF,
        dont le siège social est situé [À COMPLÉTER : adresse complète, Polynésie française],
        immatriculée au Registre du commerce de Papeete sous le numéro
        [À COMPLÉTER : n° RC], numéro TAHITI [À COMPLÉTER : n° TAHITI].
      </p>
      <p>
        Contact&nbsp;: [À COMPLÉTER : email de contact] — Téléphone&nbsp;:
        [À COMPLÉTER : téléphone].
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Directeur de la publication</h2>
      <p>[À COMPLÉTER : nom du directeur de la publication].</p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Hébergement</h2>
      <p>
        Le site est hébergé par [À COMPLÉTER : raison sociale de l'hébergeur],
        [À COMPLÉTER : adresse de l'hébergeur] — [À COMPLÉTER : site web / téléphone de
        l'hébergeur].
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Propriété intellectuelle</h2>
      <p>
        L'ensemble des éléments du site (structure, textes, logos, charte graphique) est la
        propriété de Natimai Solutions ou fait l'objet d'une autorisation d'utilisation. Toute
        reproduction non autorisée constitue une contrefaçon.
      </p>
      <p>
        Les fiches produits (descriptions, spécifications techniques, visuels) peuvent provenir
        des catalogues des fabricants et de la base Icecat. Les marques, logos et références
        produits cités appartiennent à leurs propriétaires respectifs et ne sont utilisés qu'à
        des fins d'identification des produits.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Données personnelles et cookies</h2>
      <p>
        Les modalités de traitement de vos données personnelles et l'usage des cookies sont
        décrits dans notre
        <router-link :to="{ name: 'confidentialite' }">politique de confidentialité</router-link>.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Droit applicable</h2>
      <p>
        Le présent site et son utilisation sont régis par le droit applicable en Polynésie
        française. En cas de litige et à défaut de résolution amiable, les tribunaux de Papeete
        sont compétents, sous réserve des règles d'ordre public applicables.
      </p>
    </div>
  </q-page>
</template>

<script setup lang="ts">
// Page statique — aucun script nécessaire.
</script>

<style scoped lang="scss">
.legal-page__content {
  width: min(860px, 100%);
  margin: 0 auto;
  line-height: 1.65;
}
</style>
