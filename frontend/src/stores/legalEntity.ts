import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import { getPublicSettings } from '@/api/systemSettings';
import { LEGAL_FIELD_KEYS, resolveLegalEntity, type LegalEntity } from '@/config/legalEntity';

/**
 * Identité légale de l'éditeur, servie par le backend.
 *
 * Ces valeurs sont de la donnée de déploiement — ce dépôt est un modèle — donc
 * elles vivent dans `system_settings`, éditables depuis le back-office. Les
 * factures lisent les mêmes lignes : une facture et des mentions légales ne
 * peuvent pas annoncer des adresses différentes.
 *
 * Tant qu'une valeur n'est pas saisie, le résolveur rend un placeholder que la
 * page affiche en rouge, plutôt qu'un blanc silencieux.
 */
export const useLegalEntityStore = defineStore('legalEntity', () => {
  const values = ref<Record<string, string>>({});
  const loaded = ref(false);
  /** Requête en cours — hors `ref` : ne doit pas franchir la frontière SSR. */
  let inFlight: Promise<void> | null = null;

  const entity = computed<LegalEntity>(() => resolveLegalEntity(values.value));

  /**
   * Charge l'identité, une seule fois par état.
   *
   * `loaded` n'est posé qu'en cas de SUCCÈS, et c'est essentiel : Quasar
   * sérialise l'état Pinia du rendu serveur vers le client. Un `loaded = true`
   * posé après un échec SSR voyagerait jusqu'au navigateur, qui ne réessaierait
   * jamais et afficherait des placeholders sur une page pourtant renseignée.
   *
   * L'appel serveur échoue d'ailleurs en développement : `VITE_API_URL` est
   * l'URL vue par le NAVIGATEUR, et `localhost:8000` désigne, depuis le
   * conteneur de rendu, ce conteneur lui-même. En production l'API est sur un
   * sous-domaine public, joignable des deux côtés, donc le HTML servi est
   * complet — ce qui compte pour une page légale lue sans JavaScript.
   */
  async function load(): Promise<void> {
    if (loaded.value) return;
    // Les appels concurrents (prefetch serveur + setup) partagent la requête.
    inFlight ??= fetchSettings();
    try {
      await inFlight;
    } finally {
      inFlight = null;
    }
  }

  async function fetchSettings(): Promise<void> {
    try {
      const settings = await getPublicSettings();
      values.value = Object.fromEntries(
        settings
          .filter((s) => LEGAL_FIELD_KEYS.has(s.key) && s.value.trim())
          .map((s) => [s.key, s.value]),
      );
      loaded.value = true;
    } catch {
      // Une page légale doit s'afficher même API indisponible : les
      // placeholders rouges disent exactement ce qui manque, ce qui vaut mieux
      // qu'une page d'erreur. `loaded` reste faux pour permettre une reprise.
      values.value = {};
    }
  }

  return { entity, loaded, load };
});
