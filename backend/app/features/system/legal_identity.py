"""Identité légale de l'éditeur, stockée en base (L1).

Ces informations — raison sociale, immatriculation, hébergeur, dates — sont de
la **donnée de déploiement**, pas du code : ce dépôt est un modèle, et les
inscrire dans les sources obligerait chaque installation à les modifier.

Elles vivent donc dans ``system_settings``, éditables depuis le back-office
sans redéploiement. Deux surfaces les consomment :

* la vitrine (CGV, mentions légales, confidentialité) via l'endpoint public
  ``GET /system/settings`` — ces informations sont publiques par nature, leur
  publication est même une obligation légale ;
* les factures, qui en figent une copie à l'émission.

Une seule source à l'exécution, donc : une facture et des mentions légales ne
peuvent plus annoncer des adresses différentes.

Les variables ``INVOICE_SELLER_*`` ne servent plus qu'à **amorcer** la base au
premier démarrage, pour qu'un déploiement existant ne reparte pas de zéro.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings


@dataclass(frozen=True)
class LegalSettingSpec:
    """Une information d'identité : sa description admin et son amorçage."""

    key: str
    description: str
    #: Nom du réglage d'environnement utilisé comme valeur initiale, s'il existe.
    seed_from_setting: str | None = None


#: Ordre d'affichage dans l'écran admin — identité, puis contact, puis contenu.
LEGAL_SETTINGS: tuple[LegalSettingSpec, ...] = (
    LegalSettingSpec(
        "legal_trading_name",
        "Nom commercial affiché sur le site et les factures",
        "INVOICE_SELLER_NAME",
    ),
    LegalSettingSpec("legal_form", "Forme juridique (SARL, SAS…)"),
    LegalSettingSpec(
        "legal_share_capital",
        f"Capital social, en {settings.REFERENCE_CURRENCY} (montant seul)",
    ),
    LegalSettingSpec(
        "legal_head_office_address",
        "Adresse complète du siège social",
        "INVOICE_SELLER_ADDRESS",
    ),
    LegalSettingSpec("legal_rc_number", settings.territory_profile.registry_label),
    LegalSettingSpec(
        "legal_tahiti_number",
        settings.territory_profile.registration_label,
        "INVOICE_SELLER_REGISTRATION",
    ),
    LegalSettingSpec("legal_tax_id", "Identifiant fiscal"),
    LegalSettingSpec(
        "legal_contact_email", "Email de contact général", "INVOICE_SELLER_EMAIL"
    ),
    LegalSettingSpec(
        "legal_contact_phone",
        "Téléphone de contact affiché sur le site et les factures",
        "INVOICE_SELLER_PHONE",
    ),
    LegalSettingSpec(
        "legal_publication_director",
        "Directeur de la publication (personne physique responsable du contenu)",
    ),
    LegalSettingSpec("legal_host_name", "Raison sociale de l'hébergeur du site"),
    LegalSettingSpec("legal_host_address", "Adresse de l'hébergeur"),
    LegalSettingSpec("legal_host_contact", "Site web ou téléphone de l'hébergeur"),
    LegalSettingSpec("legal_support_email", "Email du service après-vente"),
    LegalSettingSpec(
        "legal_cgv_version_date", "Date de mise en vigueur de la version des CGV"
    ),
    LegalSettingSpec(
        "legal_privacy_updated_date",
        "Date de dernière mise à jour de la politique de confidentialité",
    ),
    LegalSettingSpec(
        "legal_delivery_reservation_delay",
        "Délai pour formuler une réserve à la livraison (ex. 3 jours ouvrés)",
    ),
    LegalSettingSpec(
        "legal_withdrawal_regime",
        "Régime de rétractation applicable à la vente à distance en Polynésie "
        "française — À FAIRE VALIDER PAR UN CONSEIL JURIDIQUE",
    ),
    LegalSettingSpec(
        "legal_mediation_scheme",
        "Dispositif de médiation de la consommation applicable — À VALIDER",
    ),
    LegalSettingSpec(
        "legal_invoice_retention",
        "Durée de conservation des données de facturation (ex. 10 ans)",
    ),
    LegalSettingSpec(
        "legal_technical_log_retention",
        "Durée de conservation des journaux techniques (ex. 12 mois)",
    ),
    LegalSettingSpec(
        "legal_payment_terms",
        "Conditions de règlement affichées en bas de facture",
    ),
    LegalSettingSpec(
        "legal_late_penalty_terms",
        "Pénalités de retard affichées en bas de facture",
    ),
)

LEGAL_SETTING_KEYS: frozenset[str] = frozenset(spec.key for spec in LEGAL_SETTINGS)

#: Sous-ensemble sans lequel une facture n'est pas un document comptable
#: valable : qui vend, où, et sous quel numéro.
REQUIRED_FOR_INVOICING: tuple[str, ...] = (
    "legal_trading_name",
    "legal_head_office_address",
    "legal_tahiti_number",
)


def seed_value_for(spec: LegalSettingSpec) -> str:
    """Valeur initiale d'une clé, tirée de l'environnement quand elle existe."""
    if spec.seed_from_setting is None:
        return ""
    return str(getattr(settings, spec.seed_from_setting, "") or "").strip()


async def load_legal_identity(session: AsyncSession) -> dict[str, str]:
    """Toutes les valeurs d'identité connues, indexées par clé.

    Les clés absentes ou vides ne sont pas retournées : l'appelant décide
    comment signaler un manque (placeholder rouge sur la vitrine, marqueur sur
    le PDF), ce qui vaut mieux qu'une chaîne vide silencieuse.
    """
    from app.core import runtime_settings

    values = await runtime_settings.get_many(sorted(LEGAL_SETTING_KEYS), session)
    return {
        key: str(value) for key, value in values.items() if str(value or "").strip()
    }


def missing_for_invoicing(identity: dict[str, str]) -> list[str]:
    """Clés indispensables à la facturation qui restent vides."""
    return [key for key in REQUIRED_FOR_INVOICING if not identity.get(key, "").strip()]
