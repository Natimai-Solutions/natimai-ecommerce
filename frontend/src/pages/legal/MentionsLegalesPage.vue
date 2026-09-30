<!--
  Mentions légales — DOCUMENT À FAIRE VALIDER PAR UN CONSEIL JURIDIQUE avant
  mise en ligne.

  Les données d'identité viennent de la base (system_settings, clés legal_*),
  éditables depuis le back-office et partagées avec les factures. Les valeurs
  non renseignées s'affichent en rouge et font échouer
  scripts/release/check-legal-placeholders.sh.
-->
<template>
  <!-- Une page publiée depuis l'admin (« Pages du site », slug mentions-legales) remplace ce texte. -->
  <DbContentPage slug="mentions-legales" fallback-title="Mentions légales">
    <template #fallback>
      <h1>Mentions légales</h1>

      <h2>Éditeur du site</h2>
      <p>
        Le présent site est édité par <strong>{{ legalEntity.tradingName }}</strong
        >, <LegalValue :value="legalEntity.legalForm" /> au capital de
        <LegalValue :value="legalEntity.shareCapital" />&nbsp;XPF, dont le siège social est situé
        <LegalValue :value="legalEntity.headOfficeAddress" />, immatriculée au Registre du commerce
        de Papeete sous le numéro <LegalValue :value="legalEntity.rcNumber" />, numéro TAHITI
        <LegalValue :value="legalEntity.tahitiNumber" />.
      </p>
      <p>
        Contact&nbsp;: <LegalValue :value="legalEntity.contactEmail" />. Téléphone&nbsp;:
        <LegalValue :value="legalEntity.contactPhone" />.
      </p>

      <h2>Directeur de la publication</h2>
      <p><LegalValue :value="legalEntity.publicationDirector" />.</p>

      <h2>Hébergement</h2>
      <p>
        Le site est hébergé par <LegalValue :value="legalEntity.hostName" />,
        <LegalValue :value="legalEntity.hostAddress" />,
        <LegalValue :value="legalEntity.hostContact" />.
      </p>

      <h2>Propriété intellectuelle</h2>
      <p>
        L'ensemble des éléments du site (structure, textes, logos, charte graphique) est la
        propriété de {{ legalEntity.tradingName }} ou fait l'objet d'une autorisation d'utilisation.
        Toute reproduction non autorisée constitue une contrefaçon.
      </p>
      <p>
        Les fiches produits (descriptions, spécifications techniques, visuels) peuvent provenir des
        catalogues des fabricants et de la base Icecat. Les marques, logos et références produits
        cités appartiennent à leurs propriétaires respectifs et ne sont utilisés qu'à des fins
        d'identification des produits.
      </p>

      <h2>Données personnelles et cookies</h2>
      <p>
        Les modalités de traitement de vos données personnelles et l'usage des cookies sont décrits
        dans notre
        <router-link :to="{ name: 'confidentialite' }">politique de confidentialité</router-link>.
      </p>

      <h2>Droit applicable</h2>
      <p>
        Le présent site et son utilisation sont régis par le droit applicable en Polynésie
        française. En cas de litige et à défaut de résolution amiable, les tribunaux de Papeete sont
        compétents, sous réserve des règles d'ordre public applicables.
      </p>
    </template>
  </DbContentPage>
</template>

<script setup lang="ts">
import DbContentPage from '@/components/DbContentPage.vue';
import { computed, onServerPrefetch } from 'vue';
import LegalValue from '@/components/LegalValue.vue';
import { useLegalEntityStore } from '@/stores/legalEntity';

const store = useLegalEntityStore();
// Chargé côté serveur pendant le rendu SSR : la page arrive complète, sans
// clignotement de placeholders puis remplacement à l'hydratation.
onServerPrefetch(() => store.load());
void store.load();

const legalEntity = computed(() => store.entity);
</script>
