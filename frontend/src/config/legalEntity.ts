/**
 * Forme de l'identité légale de l'éditeur, et rendu des champs non renseignés.
 *
 * Les **valeurs** ne sont pas ici : ce dépôt est un modèle, et l'état civil
 * d'une société est de la donnée de déploiement. Elles vivent dans
 * `system_settings` côté backend (clés `legal_*`), éditables depuis le
 * back-office et servies par `GET /system/settings`. Les factures lisent les
 * mêmes lignes — une facture et des mentions légales ne peuvent donc pas
 * annoncer des adresses différentes.
 *
 * Ce module ne garde que la forme typée, la correspondance champ ↔ clé, et le
 * texte affiché tant qu'une valeur manque.
 */

/** Préfixe reconnu par `scripts/release/check-legal-placeholders.sh`. */
export const LEGAL_PLACEHOLDER_PREFIX = '[À COMPLÉTER';

/** Une valeur est-elle encore manquante ? */
export function isLegalPlaceholder(value: string): boolean {
  return value.startsWith(LEGAL_PLACEHOLDER_PREFIX);
}

export interface LegalEntity {
  tradingName: string;
  legalForm: string;
  /** Montant seul, en XPF ; l'unité est ajoutée par la page. */
  shareCapital: string;
  headOfficeAddress: string;
  /** Numéro au Registre du commerce de Papeete. */
  rcNumber: string;
  /** Numéro TAHITI (l'équivalent local du SIRET). */
  tahitiNumber: string;
  contactEmail: string;
  contactPhone: string;
  /** Personne physique responsable du contenu publié. */
  publicationDirector: string;
  hostName: string;
  hostAddress: string;
  hostContact: string;
  supportEmail: string;
  cgvVersionDate: string;
  privacyUpdatedDate: string;
  deliveryReservationDelay: string;
  /** Régime de rétractation — question juridique, pas de la saisie. */
  withdrawalRegime: string;
  mediationScheme: string;
  invoiceRetention: string;
  technicalLogRetention: string;
}

/**
 * Champ du modèle → clé `system_settings` + libellé affiché tant qu'il manque.
 *
 * Les clés doivent correspondre à `LEGAL_SETTINGS` côté backend
 * (`app/features/system/legal_identity.py`) ; un test le vérifie.
 */
export const LEGAL_FIELDS: ReadonlyArray<{
  field: keyof LegalEntity;
  key: string;
  missing: string;
}> = [
  { field: 'tradingName', key: 'legal_trading_name', missing: 'raison sociale' },
  { field: 'legalForm', key: 'legal_form', missing: 'forme juridique, ex. SARL' },
  { field: 'shareCapital', key: 'legal_share_capital', missing: 'capital social' },
  {
    field: 'headOfficeAddress',
    key: 'legal_head_office_address',
    missing: 'adresse complète du siège, Polynésie française',
  },
  { field: 'rcNumber', key: 'legal_rc_number', missing: 'n° RC Papeete' },
  { field: 'tahitiNumber', key: 'legal_tahiti_number', missing: 'n° TAHITI' },
  { field: 'contactEmail', key: 'legal_contact_email', missing: 'email de contact' },
  { field: 'contactPhone', key: 'legal_contact_phone', missing: 'téléphone' },
  {
    field: 'publicationDirector',
    key: 'legal_publication_director',
    missing: 'nom du directeur de la publication',
  },
  { field: 'hostName', key: 'legal_host_name', missing: "raison sociale de l'hébergeur" },
  { field: 'hostAddress', key: 'legal_host_address', missing: "adresse de l'hébergeur" },
  {
    field: 'hostContact',
    key: 'legal_host_contact',
    missing: "site web ou téléphone de l'hébergeur",
  },
  { field: 'supportEmail', key: 'legal_support_email', missing: 'email du service après-vente' },
  {
    field: 'cgvVersionDate',
    key: 'legal_cgv_version_date',
    missing: 'date de mise en vigueur des CGV',
  },
  {
    field: 'privacyUpdatedDate',
    key: 'legal_privacy_updated_date',
    missing: 'date de dernière mise à jour',
  },
  {
    field: 'deliveryReservationDelay',
    key: 'legal_delivery_reservation_delay',
    missing: 'délai de réserve, ex. 3 jours ouvrés',
  },
  {
    field: 'withdrawalRegime',
    key: 'legal_withdrawal_regime',
    missing:
      'régime de rétractation applicable à la vente à distance en Polynésie ' +
      'française — À FAIRE VALIDER PAR UN CONSEIL JURIDIQUE',
  },
  {
    field: 'mediationScheme',
    key: 'legal_mediation_scheme',
    missing: 'dispositif de médiation de la consommation applicable en Polynésie française',
  },
  {
    field: 'invoiceRetention',
    key: 'legal_invoice_retention',
    missing: 'durée de conservation, ex. 10 ans',
  },
  {
    field: 'technicalLogRetention',
    key: 'legal_technical_log_retention',
    missing: 'durée, ex. 12 mois',
  },
];

/** Clés `legal_*` que la vitrine consomme. */
export const LEGAL_FIELD_KEYS: ReadonlySet<string> = new Set(LEGAL_FIELDS.map((f) => f.key));

/** Construit l'identité affichable à partir des valeurs servies par l'API. */
export function resolveLegalEntity(values: Record<string, string>): LegalEntity {
  // Toutes les clés de LegalEntity sont couvertes par LEGAL_FIELDS — un test
  // le vérifie —, donc l'objet est complet à la sortie de la boucle.
  const entity = {} as Record<keyof LegalEntity, string>;
  for (const { field, key, missing } of LEGAL_FIELDS) {
    const value = (values[key] ?? '').trim();
    entity[field] = value || `${LEGAL_PLACEHOLDER_PREFIX} : ${missing}]`;
  }
  return entity;
}
