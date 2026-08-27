<!--
  Conditions générales de vente — DOCUMENT À FAIRE VALIDER PAR UN CONSEIL
  JURIDIQUE avant mise en ligne (en particulier : régime de rétractation et
  médiation applicables en Polynésie française).

  Les données d'identité viennent de la base (system_settings, clés legal_*),
  éditables depuis le back-office et partagées avec les factures.
-->
<template>
  <q-page class="legal-page q-pa-md">
    <div class="legal-page__content">
      <h1 class="text-h4 text-weight-bold q-mb-xs">Conditions générales de vente</h1>
      <p class="text-caption text-grey-7 q-mb-lg">
        Version du <LegalValue :value="legalEntity.cgvVersionDate" />.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 1 — Identité du vendeur</h2>
      <p>
        <strong>{{ legalEntity.tradingName }}</strong>,
        <LegalValue :value="legalEntity.legalForm" />, siège social
        <LegalValue :value="legalEntity.headOfficeAddress" />, RC Papeete n°
        <LegalValue :value="legalEntity.rcNumber" />, n° TAHITI
        <LegalValue :value="legalEntity.tahitiNumber" />, email
        <LegalValue :value="legalEntity.contactEmail" /> (ci-après « le Vendeur »).
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 2 — Champ d'application</h2>
      <p>
        Les présentes conditions générales de vente (CGV) s'appliquent à toute commande passée
        sur le présent site par un client professionnel ou particulier livré en Polynésie
        française. La validation d'une commande emporte acceptation sans réserve des CGV en
        vigueur au jour de la commande.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 3 — Produits et disponibilité</h2>
      <p>
        Les produits proposés sont des matériels et équipements importés, décrits sur leurs
        fiches respectives à partir des données des fabricants. Les photographies et
        spécifications sont fournies à titre indicatif dans la limite des données transmises par
        les fabricants. Les produits sont proposés dans la limite des stocks disponibles chez le
        Vendeur et ses fournisseurs&nbsp;; en cas d'indisponibilité constatée après commande, le
        client en est informé et peut choisir entre un produit équivalent, un avoir ou le
        remboursement des sommes versées.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 4 — Prix</h2>
      <p>
        Les prix sont exprimés en francs pacifiques (XPF) toutes taxes comprises. Ils intègrent
        le coût du produit, le fret international selon le mode d'acheminement choisi (aérien ou
        maritime), les droits et taxes d'importation en Polynésie française ainsi que la TVA
        locale applicable. Les frais de livraison locale (acheminement jusqu'à l'adresse ou au
        point de retrait) sont indiqués avant la validation de la commande.
      </p>
      <p>
        Les prix affichés au catalogue sont susceptibles d'évoluer à tout moment, notamment en
        fonction des tarifs fournisseurs et des taux de change&nbsp;; le prix applicable est
        celui confirmé au moment de la validation de la commande ou du devis accepté.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 5 — Commande et devis</h2>
      <p>
        La commande est passée en ligne via le panier, ou par acceptation d'un devis établi par
        le Vendeur. Le Vendeur se réserve le droit de refuser ou d'annuler une commande en cas
        de litige antérieur, d'impossibilité d'approvisionnement ou d'erreur manifeste de prix,
        moyennant remboursement intégral des sommes versées.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 6 — Paiement</h2>
      <p>
        Le règlement s'effectue selon les moyens proposés au moment de la commande&nbsp;:
        carte bancaire (paiement sécurisé PayZen&nbsp;/&nbsp;Lyra), virement bancaire, chèque ou
        bon de commande pour les clients professionnels autorisés. En cas de paiement par carte,
        le Vendeur peut procéder à une autorisation à la commande suivie d'un débit au moment de
        l'expédition. La commande n'est traitée qu'après encaissement effectif ou validation du
        moyen de paiement.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 7 — Livraison</h2>
      <p>
        Les livraisons sont assurées en Polynésie française, sur les îles desservies indiquées
        au moment de la commande. Les délais affichés sont indicatifs&nbsp;: ils dépendent du
        mode d'acheminement choisi (aérien ou maritime), des délais fournisseurs, du transport
        international, du dédouanement et de la desserte inter-îles. Un retard de livraison
        n'ouvre droit à annulation que dans les conditions prévues par la réglementation
        applicable, après mise en demeure restée infructueuse.
      </p>
      <p>
        Le client vérifie l'état du colis à la réception et formule toute réserve auprès du
        transporteur et du Vendeur dans les meilleurs délais, au plus tard sous
        <LegalValue :value="legalEntity.deliveryReservationDelay" />.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 8 — Droit de rétractation</h2>
      <!--
        À arrêter avec le conseil juridique : délai, modalités d'exercice,
        exclusions (produits déscellés, logiciels, produits personnalisés…),
        frais de retour. À défaut de régime obligatoire en Polynésie française,
        énoncer la politique commerciale de retour du Vendeur.
      -->
      <p>
        <LegalValue :value="legalEntity.withdrawalRegime" />
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 9 — Garanties et SAV</h2>
      <p>
        Les produits bénéficient de la garantie légale applicable ainsi que, le cas échéant, de
        la garantie commerciale du fabricant (dont la durée et les conditions figurent sur la
        fiche produit ou la documentation constructeur). Le Vendeur, en qualité d'importateur,
        est l'interlocuteur du client pour la mise en œuvre des garanties&nbsp;: la demande est
        formulée auprès du service client à <LegalValue :value="legalEntity.supportEmail" />.
        Les délais de traitement
        peuvent inclure un retour du matériel vers le fabricant ou son centre agréé hors de
        Polynésie française.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 10 — Responsabilité</h2>
      <p>
        La responsabilité du Vendeur ne saurait être engagée en cas d'inexécution imputable au
        client, au fait imprévisible et insurmontable d'un tiers ou à un cas de force majeure
        (notamment interruption des liaisons maritimes ou aériennes, décisions douanières,
        catastrophes naturelles). Pour les clients professionnels, la responsabilité du Vendeur
        est en toute hypothèse limitée au montant de la commande concernée.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 11 — Données personnelles</h2>
      <p>
        Les données collectées dans le cadre de la commande sont traitées conformément à la
        <router-link :to="{ name: 'confidentialite' }">politique de confidentialité</router-link>.
      </p>

      <h2 class="text-h6 q-mt-lg q-mb-sm">Article 12 — Droit applicable et litiges</h2>
      <p>
        Les présentes CGV sont soumises au droit applicable en Polynésie française. En cas de
        litige, le client s'adresse en priorité au service client afin de rechercher une
        solution amiable. <LegalValue :value="legalEntity.mediationScheme" />
        À défaut, les tribunaux de Papeete sont compétents, sous réserve des
        règles d'ordre public applicables.
      </p>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onServerPrefetch } from 'vue';
import LegalValue from 'src/components/LegalValue.vue';
import { useLegalEntityStore } from 'src/stores/legalEntity';

const store = useLegalEntityStore();
// Chargé côté serveur pendant le rendu SSR : la page arrive complète, sans
// clignotement de placeholders puis remplacement à l'hydratation.
onServerPrefetch(() => store.load());
void store.load();

const legalEntity = computed(() => store.entity);
</script>

<style scoped lang="scss">
.legal-page__content {
  width: min(860px, 100%);
  margin: 0 auto;
  line-height: 1.65;
}
</style>
