"""The catalogue of runtime settings (R5): what the owner edits in base.

Each entry is a :class:`~app.core.runtime_settings.SettingSpec`. Keys already
stored by earlier versions keep their name (``pricing_*``, ``legal_*``,
``tax_*``, ``payment_*``, ``customs_free_countries``, ``social_webhook_url``,
``default_display_currency``) so no data moves.

What stays in the environment: infrastructure, secrets and integration
credentials, the structural choices of the deployment (territory profile,
``SHOP_MODE``, reference currency…) and the e-mail provider (a strict
``Literal``, N13). The module switches (``module.*``) have their own registry
and screen (``modules.py``).

Imported lazily by ``app.core.runtime_settings`` on first use.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.core.i18n import SUPPORTED_LOCALES
from app.core.runtime_settings import SettingSpec, register, register_hook
from app.features.payment.services.provider_settings import (
    PSP_DEFAULTS,
    PSP_LABELS,
)
from app.features.payment.services.provider_settings import (
    setting_key as psp_setting_key,
)
from app.features.product.services.pricing_parameters import PRICING_SETTINGS
from app.features.system.legal_identity import LEGAL_SETTINGS
from app.features.system.payment_instructions import PAYMENT_INSTRUCTION_SETTINGS

#: Categories, in display order: ``key → (label, help)``.
CATEGORIES: dict[str, tuple[str, str]] = {
    "shop": ("Boutique", "Nom, adresses de contact, version des CGV."),
    "legal": (
        "Identité légale",
        "Publiée sur la vitrine (mentions légales, CGV) et figée sur chaque facture.",
    ),
    "pricing": (
        "Prix",
        "Paramètres de la formule de prix : une modification recalcule le catalogue.",
    ),
    "tax": ("Taxes", "Taux appliqués par défaut (codes des taux de TVA)."),
    "invoice": ("Factures", "Mentions imprimées sur les factures."),
    "payment": (
        "Paiement",
        "Prestataires activés et instructions des paiements manuels.",
    ),
    "notifications": ("Notifications", "E-mails et alertes envoyés par la boutique."),
    "orders": (
        "Commandes et stock",
        "Réservations, paniers abandonnés, vérifications.",
    ),
    "suppliers": ("Fournisseurs", "Synchronisation et import des catalogues."),
    "icecat": ("Icecat", "Enrichissement des fiches produit."),
    "logistics": ("Logistique", "Douane et départs groupés."),
    "display": (
        "Affichage",
        "Langues et devises proposées au visiteur de la vitrine.",
    ),
    "security": ("Sécurité", "Permissions et conservation du journal d'audit."),
}

ZERO = Decimal("0")


def _d(value: str | int) -> Decimal:
    return Decimal(str(value))


async def _reprice(_session: Any, spec: SettingSpec, _resolved: Any) -> None:
    from app.tasks.pricing_tasks import schedule_price_refresh

    await schedule_price_refresh(reason=f"system_setting:{spec.key}")


register_hook("reprice", _reprice)


# --------------------------------------------------------------------------
# Boutique

register(
    SettingSpec(
        "shop_name",
        "str",
        "shop",
        "Nom de la boutique",
        "Affiché dans les e-mails, l'en-tête de la vitrine et l'application "
        "d'authentification des administrateurs.",
        env="SHOP_NAME",
        public=True,
        max_length=100,
        order=10,
    ),
    SettingSpec(
        "shop_logo_media_id",
        "str",
        "shop",
        "Logo",
        "Image de la médiathèque (usage « Identité visuelle ») affichée dans "
        "l'en-tête de la vitrine, les e-mails et les PDF. Vide = le nom de la "
        "boutique en texte. Se règle depuis Système → Identité visuelle.",
        default="",
        public=True,
        max_length=36,
        order=12,
    ),
    SettingSpec(
        "shop_icon_media_id",
        "str",
        "shop",
        "Icône du site",
        "Image carrée de la médiathèque : favicon et icône d'écran d'accueil de la "
        "vitrine (tailles dérivées automatiquement). Vide = icône par défaut. Se "
        "règle depuis Système → Identité visuelle.",
        default="",
        public=True,
        max_length=36,
        order=13,
    ),
    SettingSpec(
        "email_support",
        "str",
        "shop",
        "E-mail du service client",
        "Adresse indiquée aux clients dans les e-mails (devis, paiement). "
        "Vide = aucune adresse affichée.",
        env="EMAIL_SUPPORT",
        format="email",
        max_length=255,
        order=20,
    ),
    SettingSpec(
        "email_contact",
        "str",
        "shop",
        "E-mail de contact",
        "Destinataire des messages du formulaire de contact.",
        env="EMAIL_CONTACT",
        format="email",
        max_length=255,
        order=30,
    ),
    SettingSpec(
        "cgv_version",
        "str",
        "shop",
        "Version des CGV",
        "Version acceptée par le client et enregistrée sur chaque commande. "
        "À changer à chaque nouvelle version des conditions générales.",
        env="CGV_VERSION",
        public=True,
        max_length=40,
        order=40,
    ),
)

# --------------------------------------------------------------------------
# Identité légale (public by nature, seeded once from INVOICE_SELLER_*)

register(
    *(
        SettingSpec(
            spec.key,
            "text"
            if spec.key.endswith(("address", "terms", "regime", "scheme"))
            else "str",
            "legal",
            spec.description,
            "",
            default="",
            public=True,
            seed_env=spec.seed_from_setting,
            max_length=2000,
            order=index,
        )
        for index, spec in enumerate(LEGAL_SETTINGS)
    )
)

# --------------------------------------------------------------------------
# Prix

register(
    *(
        SettingSpec(
            spec.key,
            "decimal",
            "pricing",
            (
                "Commission de paiement (%)"
                if "commission" in spec.key
                else "Marge de sécurité sur le change (%)"
            ),
            spec.description,
            default=spec.default,
            minimum=spec.minimum,
            below=spec.below,
            on_change=("reprice",),
            order=index * 10,
            extra={"unit": "%"},
        )
        for index, spec in enumerate(PRICING_SETTINGS)
    ),
    SettingSpec(
        "insurance_rate_pct",
        "decimal",
        "pricing",
        "Assurance transport (%)",
        "Taux d'assurance du fret import, en % de la valeur des marchandises "
        "(entre dans l'assiette CAF de la douane). 0 = non facturée. Modifier "
        "cette valeur recalcule tous les prix.",
        env="INSURANCE_RATE_PCT",
        minimum=ZERO,
        below=_d(100),
        on_change=("reprice",),
        order=30,
        extra={"unit": "%"},
    ),
)

# --------------------------------------------------------------------------
# Taxes

register(
    SettingSpec(
        "tax_default_code",
        "str",
        "tax",
        "Taux par défaut des articles",
        "Code du taux de TVA appliqué quand ni l'article ni sa catégorie n'en "
        "précisent. Modifier cette valeur recalcule tous les prix.",
        env="DEFAULT_TAX_CODE",
        upper=True,
        max_length=50,
        on_change=("reprice",),
        order=10,
    ),
    SettingSpec(
        "tax_fees_code",
        "str",
        "tax",
        "Taux des frais",
        "Code du taux de TVA des frais (livraison, paiement, acompte) sur les "
        "factures.",
        env="INVOICE_FEES_TAX_CODE",
        upper=True,
        max_length=50,
        order=20,
    ),
)

# --------------------------------------------------------------------------
# Factures

register(
    SettingSpec(
        "invoice_legal_footer",
        "text",
        "invoice",
        "Pied de facture",
        "Mentions libres ajoutées en bas de chaque facture.",
        env="INVOICE_LEGAL_FOOTER",
        max_length=2000,
        order=10,
    ),
)

# --------------------------------------------------------------------------
# Paiement

register(
    *(
        SettingSpec(
            psp_setting_key(code),
            "bool",
            "payment",
            f"{PSP_LABELS[code]} activé",
            "Les identifiants restent dans l'environnement : un prestataire "
            "activé sans identifiants reste indisponible.",
            default=default,
            order=index,
        )
        for index, (code, default) in enumerate(PSP_DEFAULTS.items())
    ),
    *(
        SettingSpec(
            spec.key,
            "text",
            "payment",
            {
                "manual_cash": "Instructions — espèces",
                "manual_check": "Instructions — chèque",
                "manual_transfer": "Instructions — virement",
            }.get(spec.provider_code, spec.provider_code),
            spec.description,
            default="",
            max_length=2000,
            order=10 + index,
        )
        for index, spec in enumerate(PAYMENT_INSTRUCTION_SETTINGS)
    ),
)

register(
    SettingSpec(
        "payment_auto_capture_status",
        "str",
        "payment",
        "Capture automatique des autorisations carte",
        "Avec la validation manuelle PayZen, la carte est seulement autorisée au "
        "checkout : le débit (capture) part de lui-même quand la commande atteint "
        "cette étape. Vide = capture à la main depuis Paiements.",
        default="InTransit",
        choices=(
            "",
            "OrderedFromSupplier",
            "InTransit",
            "AtCustoms",
            "Received",
            "ReadyForPickup",
            "Delivered",
        ),
        order=20,
    ),
    SettingSpec(
        "payment_void_on_cancel",
        "bool",
        "payment",
        "Libérer l'autorisation carte à l'annulation",
        "Une commande annulée avant capture libère la réservation sur la carte "
        "du client (annulation de l'autorisation chez le prestataire).",
        default=True,
        order=21,
    ),
    SettingSpec(
        "payment_authorization_validity_days",
        "int",
        "payment",
        "Durée de validité d'une autorisation carte (jours)",
        "Au-delà, la banque du client libère la réservation et la capture "
        "échoue. La veille, une alerte part vers le webhook d'exploitation pour "
        "chaque autorisation non capturée. 0 = pas d'alerte.",
        default=7,
        minimum=ZERO,
        maximum=_d(30),
        order=22,
        extra={"unit": "j"},
    ),
)

# --------------------------------------------------------------------------
# Notifications

register(
    SettingSpec(
        "notifications_email_enabled",
        "bool",
        "notifications",
        "E-mails aux clients",
        "Confirmations de commande, de paiement, d'expédition, devis, alertes "
        "de stock. Désactivé : aucun e-mail client n'est envoyé.",
        env="PAYMENT_NOTIFICATIONS_EMAIL_ENABLED",
        order=10,
    ),
    SettingSpec(
        "notifications_slack_enabled",
        "bool",
        "notifications",
        "Alertes Slack",
        "Message Slack à chaque paiement (adresse du webhook ci-dessous).",
        env="PAYMENT_NOTIFICATIONS_SLACK_ENABLED",
        order=20,
    ),
    SettingSpec(
        "notifications_slack_webhook_url",
        "str",
        "notifications",
        "Webhook Slack",
        "Adresse https du webhook entrant Slack.",
        env="PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL",
        format="url",
        secret=True,
        max_length=500,
        order=30,
    ),
)

# --------------------------------------------------------------------------
# Commandes et stock

register(
    SettingSpec(
        "stock_reservation_ttl_hours",
        "int",
        "orders",
        "Durée de réservation du stock (heures)",
        "Le stock réservé par une commande sans issue de paiement est libéré "
        "après ce délai. 0 = jamais.",
        env="STOCK_RESERVATION_TTL_HOURS",
        minimum=ZERO,
        maximum=_d(24 * 60),
        order=10,
        extra={"unit": "h"},
    ),
    SettingSpec(
        "dashboard_low_stock_threshold",
        "int",
        "orders",
        "Seuil de stock bas (tableau de bord)",
        "Un produit vendu sur stock dont il reste au plus ce nombre d'unités "
        "vendables compte dans « Stocks bas » sur le tableau de bord.",
        default=2,
        minimum=ZERO,
        maximum=_d(10_000),
        order=15,
        extra={"unit": "unités"},
    ),
    SettingSpec(
        "cart_abandonment_reminder_delay_hours",
        "int",
        "orders",
        "Relance des paniers abandonnés (heures)",
        "Délai d'inactivité avant l'e-mail de relance. 0 = pas de relance.",
        env="CART_ABANDONMENT_REMINDER_DELAY_HOURS",
        minimum=ZERO,
        maximum=_d(24 * 30),
        order=20,
        extra={"unit": "h"},
    ),
    SettingSpec(
        "cart_abandonment_max_age_days",
        "int",
        "orders",
        "Âge maximal d'un panier relancé (jours)",
        "Un panier plus ancien n'est plus relancé.",
        env="CART_ABANDONMENT_MAX_AGE_DAYS",
        minimum=_d(1),
        maximum=_d(365),
        order=30,
        extra={"unit": "j"},
    ),
    SettingSpec(
        "checkout_supplier_availability_check",
        "bool",
        "orders",
        "Vérifier la disponibilité fournisseur au paiement",
        "Interroge le fournisseur avant le paiement des articles sans stock propre.",
        env="CHECKOUT_SUPPLIER_AVAILABILITY_CHECK",
        order=40,
    ),
    SettingSpec(
        "checkout_supplier_check_timeout_seconds",
        "float",
        "orders",
        "Délai maximal de cette vérification (secondes)",
        "Au-delà, la commande continue sans réponse du fournisseur.",
        env="CHECKOUT_SUPPLIER_CHECK_TIMEOUT_SECONDS",
        minimum=_d(1),
        maximum=_d(60),
        order=50,
        extra={"unit": "s"},
    ),
)

# --------------------------------------------------------------------------
# Fournisseurs

register(
    SettingSpec(
        "supplier_delisting_grace_hours",
        "int",
        "suppliers",
        "Délai avant retrait d'un article disparu (heures)",
        "Un article absent du catalogue fournisseur depuis ce délai est désactivé.",
        env="SUPPLIER_DELISTING_GRACE_HOURS",
        minimum=ZERO,
        maximum=_d(24 * 90),
        order=10,
        extra={"unit": "h"},
    ),
    SettingSpec(
        "supplier_file_import_inline_max_rows",
        "int",
        "suppliers",
        "Import immédiat jusqu'à (lignes)",
        "Au-delà, l'import de fichier passe en tâche de fond.",
        env="SUPPLIER_FILE_IMPORT_INLINE_MAX_ROWS",
        minimum=_d(1),
        maximum=_d(100_000),
        order=20,
    ),
    SettingSpec(
        "supplier_file_import_max_rows",
        "int",
        "suppliers",
        "Taille maximale d'un fichier importé (lignes)",
        "Un fichier plus long est refusé.",
        env="SUPPLIER_FILE_IMPORT_MAX_ROWS",
        minimum=_d(1),
        maximum=_d(5_000_000),
        order=30,
    ),
)

# --------------------------------------------------------------------------
# Icecat

register(
    SettingSpec(
        "icecat_use_open",
        "bool",
        "icecat",
        "Open Icecat (gratuit)",
        "Désactivé : Full Icecat (abonnement, identifiants requis).",
        env="ICECAT_USE_OPEN",
        order=10,
    ),
    SettingSpec(
        "icecat_language",
        "str",
        "icecat",
        "Langue des fiches",
        "Code de langue Icecat des descriptions importées.",
        env="ICECAT_LANGUAGE",
        choices=("fr", "en", "de", "es", "it", "nl", "pt"),
        order=20,
    ),
    SettingSpec(
        "icecat_enrichment_interval_hours",
        "int",
        "icecat",
        "Enrichissement automatique toutes les (heures)",
        "Fréquence du traitement des articles non enrichis. 0 = jamais.",
        env="ICECAT_ENRICHMENT_CRON_INTERVAL_HOURS",
        minimum=ZERO,
        maximum=_d(24 * 7),
        order=30,
        extra={"unit": "h"},
    ),
    SettingSpec(
        "icecat_batch_enrich_limit",
        "int",
        "icecat",
        "Articles par lot",
        "Nombre d'articles enrichis par passage.",
        env="ICECAT_BATCH_ENRICH_LIMIT",
        minimum=_d(1),
        maximum=_d(1000),
        order=40,
    ),
    SettingSpec(
        "icecat_enrichment_retry_cooldown_days",
        "int",
        "icecat",
        "Nouvel essai après (jours)",
        "Un article sans correspondance Icecat n'est réessayé qu'après ce délai.",
        env="ICECAT_ENRICHMENT_RETRY_COOLDOWN_DAYS",
        minimum=ZERO,
        maximum=_d(365),
        order=50,
        extra={"unit": "j"},
    ),
)

# --------------------------------------------------------------------------
# Logistique

register(
    SettingSpec(
        "customs_free_countries",
        "list",
        "logistics",
        "Pays sans douane",
        "Codes pays ISO (séparés par des virgules) dont les fournisseurs sont "
        "traités comme locaux : ni douane ni fret d'import dans le prix, même "
        "s'ils ne sont pas dans le pays de l'entrepôt principal (ex. union "
        "douanière). Vide = seul le pays de l'entrepôt principal est local. "
        "Modifier cette valeur recalcule tous les prix.",
        default=[],
        upper=True,
        on_change=("reprice",),
        order=10,
    ),
    SettingSpec(
        "social_webhook_url",
        "str",
        "logistics",
        "Webhook des rappels de départs",
        "URL https d'un webhook (Make, Zapier, Buffer…) recevant les rappels "
        "des départs groupés : {text, link, image_url, departure}.",
        default="",
        format="url",
        secret=True,
        max_length=500,
        order=20,
    ),
)

# --------------------------------------------------------------------------
# Affichage

register(
    SettingSpec(
        "shop_default_locale",
        "str",
        "display",
        "Langue par défaut",
        "Langue de la vitrine, des e-mails et des documents quand le visiteur "
        "n'en a pas choisi (ni préférence enregistrée, ni langue du navigateur "
        "proposée).",
        env="SHOP_DEFAULT_LOCALE",
        public=True,
        choices=SUPPORTED_LOCALES,
        order=1,
    ),
    SettingSpec(
        "shop_locales",
        "list",
        "display",
        "Langues proposées",
        "Langues offertes au visiteur dans le sélecteur de la vitrine, parmi "
        "celles livrées avec l'interface (fr, en). La langue par défaut est "
        "toujours proposée. Ajouter une nouvelle langue reste un travail de "
        "traduction de l'interface (fichiers i18n, modèles d'e-mails).",
        env="SHOP_LOCALES",
        public=True,
        choices=SUPPORTED_LOCALES,
        order=2,
    ),
    SettingSpec(
        "default_display_currency",
        "str",
        "display",
        "Devise d'affichage par défaut",
        "Devise proposée au visiteur qui n'en a pas choisi (code ISO, ex. XPF, "
        "EUR) : la devise de référence ou une devise proposée au visiteur "
        "(écran Taux de change).",
        default=settings.REFERENCE_CURRENCY,
        public=True,
        upper=True,
        max_length=3,
        order=10,
    ),
    SettingSpec(
        "hidden_display_currencies",
        "list",
        "display",
        "Devises non proposées au visiteur",
        "Codes ISO des devises qui ont un taux de change (utile au calcul des "
        "prix fournisseurs) mais que la vitrine ne propose pas comme devise "
        "d'affichage. Géré depuis l'écran Taux de change (« Désactiver »).",
        default=[],
        upper=True,
        order=20,
    ),
)

# --------------------------------------------------------------------------
# Sécurité

register(
    SettingSpec(
        "captcha_turnstile_site_key",
        "str",
        "security",
        "Turnstile — clé de site",
        "Clé publique du widget Cloudflare Turnstile affiché sur les formulaires "
        "publics de la vitrine (inscription, alerte de stock d'un visiteur, "
        "devis sans compte). Vide = pas de captcha.",
        default="",
        public=True,
        max_length=100,
        order=1,
    ),
    SettingSpec(
        "captcha_turnstile_secret",
        "str",
        "security",
        "Turnstile — clé secrète",
        "Clé secrète vérifiée auprès de Cloudflare à chaque envoi d'un formulaire "
        "public. Vide = aucune vérification (les limites de fréquence restent).",
        default="",
        secret=True,
        max_length=100,
        order=2,
    ),
    SettingSpec(
        "enable_group_permissions",
        "bool",
        "security",
        "Permissions par groupe",
        "Applique les droits des groupes d'utilisateurs aux écrans CRUD "
        "génériques (sinon : administrateur seulement).",
        env="ENABLE_GROUP_PERMISSIONS",
        order=10,
    ),
    SettingSpec(
        "audit_log_retention_days",
        "int",
        "security",
        "Conservation du journal d'audit (jours)",
        "Les entrées plus anciennes sont supprimées chaque nuit. 0 = conserver tout.",
        env="AUDIT_LOG_RETENTION_DAYS",
        minimum=ZERO,
        maximum=_d(3650),
        order=20,
        extra={"unit": "j"},
    ),
)


__all__ = ["CATEGORIES"]
