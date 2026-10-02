<!--
  Politique de confidentialité & cookies — DOCUMENT À FAIRE VALIDER PAR UN
  CONSEIL JURIDIQUE avant mise en ligne. En Polynésie française, la loi
  Informatique et Libertés s'applique dans sa version étendue au territoire
  (le RGPD n'y est pas directement applicable) ; la CNIL reste l'autorité de
  référence.

  Les données d'identité viennent de la base (system_settings, clés legal_*),
  éditables depuis le back-office et partagées avec les factures.

  Note technique : le site n'utilise aujourd'hui que des cookies et stockages
  strictement nécessaires (authentification, panier) — exemptés de recueil de
  consentement, d'où l'absence de bandeau. Si un jour des cookies de mesure
  d'audience ou publicitaires sont ajoutés, un bandeau de consentement PRÉALABLE
  devient obligatoire.
-->
<template>
  <!-- Une page publiée depuis l'admin (« Pages du site », slug confidentialite) remplace ce texte. -->
  <DbContentPage slug="confidentialite" fallback-title="Politique de confidentialité">
    <template #fallback>
      <h1>Politique de confidentialité</h1>

      <h2>Responsable de traitement</h2>
      <p>
        Le responsable du traitement des données collectées sur ce site est
        <strong>{{ legalEntity.tradingName }}</strong
        >, <LegalValue :value="legalEntity.headOfficeAddress" />. Contact&nbsp;:
        <LegalValue :value="legalEntity.contactEmail" />.
      </p>

      <h2>Données collectées et finalités</h2>
      <p>Nous collectons uniquement les données nécessaires aux finalités suivantes&nbsp;:</p>
      <ul>
        <li>
          <strong>Compte client</strong> (nom, email, mot de passe chiffré, téléphone,
          adresses)&nbsp;: création et gestion du compte, exécution des commandes.
        </li>
        <li>
          <strong>Commandes et devis</strong> (produits, montants, adresses de livraison,
          historique)&nbsp;: traitement des commandes, facturation, garanties et SAV.
        </li>
        <li>
          <strong>Paiement</strong>&nbsp;: le paiement par carte est traité par notre prestataire
          PayZen&nbsp;/&nbsp;Lyra&nbsp;;
          <strong>aucun numéro de carte n'est stocké sur nos serveurs</strong>. Nous conservons les
          références de transaction et les justificatifs (virement, chèque, bon de commande)
          nécessaires à la comptabilité.
        </li>
        <li>
          <strong>Journaux techniques</strong> (adresse IP, horodatage)&nbsp;: sécurité du service,
          prévention de la fraude et des abus (limitation des tentatives de connexion).
        </li>
      </ul>

      <h2>Destinataires et sous-traitants</h2>
      <p>
        Les données sont destinées aux services internes du Vendeur et, pour les seules opérations
        qui les concernent, à nos prestataires&nbsp;: hébergeur (<LegalValue
          :value="legalEntity.hostName"
        />), prestataire de paiement (PayZen&nbsp;/&nbsp;Lyra), service d'envoi d'emails
        transactionnels (Mailgun), fournisseurs et transporteurs pour la préparation et
        l'acheminement des commandes. Certains de ces prestataires sont situés hors de Polynésie
        française&nbsp;; les transferts sont limités aux données nécessaires à l'exécution de leur
        mission.
      </p>

      <h2>Durées de conservation</h2>
      <ul>
        <li>Compte client&nbsp;: pendant la durée de vie du compte, puis archivage limité.</li>
        <li>
          Commandes, factures et justificatifs de paiement&nbsp;: durées légales comptables et
          fiscales applicables (<LegalValue :value="legalEntity.invoiceRetention" />).
        </li>
        <li>
          Journaux techniques&nbsp;:
          <LegalValue :value="legalEntity.technicalLogRetention" /> au maximum.
        </li>
      </ul>

      <h2>Vos droits</h2>
      <p>
        Conformément à la loi Informatique et Libertés applicable en Polynésie française, vous
        disposez de droits d'accès, de rectification, d'effacement, de limitation et d'opposition
        sur vos données. Vous pouvez les exercer en écrivant à
        <LegalValue :value="legalEntity.contactEmail" />, en justifiant de votre identité. Depuis
        votre espace client (<router-link :to="{ name: 'account', query: { tab: 'profile' } }"
          >Profil et sécurité</router-link
        >), vous pouvez aussi télécharger l'ensemble de vos données au format JSON et supprimer
        votre compte : vos données personnelles sont alors effacées, seules les commandes et
        factures sont conservées, anonymisées, pendant la durée légale. Vous disposez également du
        droit d'introduire une réclamation auprès de la CNIL (<a
          href="https://www.cnil.fr"
          target="_blank"
          rel="noopener"
          >www.cnil.fr</a
        >).
      </p>

      <h2>Sécurité</h2>
      <p>
        Les mots de passe sont stockés sous forme hachée, les échanges avec le site sont chiffrés
        (HTTPS) et l'accès aux données est limité aux personnes habilitées. Les documents transmis
        (bons de commande, justificatifs) font l'objet d'une analyse antivirus avant traitement.
      </p>

      <h2>Cookies et stockage local</h2>
      <p>
        Le site n'utilise <strong>aucun cookie publicitaire ni de mesure d'audience</strong>. Seuls
        des cookies et stockages strictement nécessaires au fonctionnement du service sont utilisés.
        Ils sont à ce titre exemptés de recueil de consentement&nbsp;:
      </p>
      <div class="prose__table">
        <table>
          <thead>
            <tr>
              <th>Nom</th>
              <th>Type</th>
              <th>Finalité</th>
              <th>Durée</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>refresh_token</code></td>
              <td>Cookie HttpOnly</td>
              <td>Maintien de la session de connexion (authentification)</td>
              <td>30 jours</td>
            </tr>
            <tr>
              <td>Préférences locales</td>
              <td>Stockage local du navigateur</td>
              <td>Panier, devise d'affichage, mode de livraison, suivi d'un paiement en cours</td>
              <td>Jusqu'à suppression par vous</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Si des cookies soumis à consentement (mesure d'audience, publicité) devaient être introduits
        à l'avenir, un dispositif de recueil de consentement préalable serait mis en place avant
        leur dépôt.
      </p>

      <p class="prose__meta">
        Dernière mise à jour&nbsp;: <LegalValue :value="legalEntity.privacyUpdatedDate" />.
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
