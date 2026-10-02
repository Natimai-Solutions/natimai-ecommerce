"""Legal pages from a template (R9 / T1).

The storefront embeds a default text for the CGV, the legal notice and the
privacy policy, read as long as no page with the same slug is published from
the back-office. Those defaults used to exist only in the storefront code, so
an owner who wanted to adapt them started from a blank editor.

This module renders the same texts on the backend (``app/templates/legal/
<lang>/<slug>.html``) with the seller identity already substituted
(``system_settings``, ``legal_*`` keys), so the admin can start a page from the
template and edit it. The ``legal_*`` settings stay: they also print the seller
identity on invoices and credit notes.

A value that is still empty is rendered as a conspicuous ``[À COMPLÉTER : …]``
marker in bold — the editor keeps it, and nobody publishes it by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.system.legal_identity import LEGAL_SETTING_KEYS, load_legal_identity

# app/features/content/legal_templates.py → app/templates/legal
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "legal"
DEFAULT_LANG = "fr"

#: Same prefix as the storefront (``frontend/src/config/legalEntity.ts``) and
#: ``scripts/release/check-legal-placeholders.sh``.
PLACEHOLDER_PREFIX = "[À COMPLÉTER"


@dataclass(frozen=True)
class LegalTemplate:
    """A built-in page the admin can start from."""

    slug: str
    title: str


#: The three legal pages the storefront embeds, in menu order.
LEGAL_TEMPLATES: tuple[LegalTemplate, ...] = (
    LegalTemplate("cgv", "Conditions générales de vente"),
    LegalTemplate("mentions-legales", "Mentions légales"),
    LegalTemplate("confidentialite", "Politique de confidentialité"),
)

LEGAL_TEMPLATE_SLUGS: frozenset[str] = frozenset(t.slug for t in LEGAL_TEMPLATES)

#: What the marker says when a setting is empty — mirrors the storefront labels.
_MISSING_LABELS: dict[str, str] = {
    "legal_trading_name": "raison sociale",
    "legal_form": "forme juridique, ex. SARL",
    "legal_share_capital": "capital social",
    "legal_head_office_address": "adresse complète du siège, Polynésie française",
    "legal_rc_number": "n° RC Papeete",
    "legal_tahiti_number": "n° TAHITI",
    "legal_tax_id": "identifiant fiscal",
    "legal_contact_email": "email de contact",
    "legal_contact_phone": "téléphone",
    "legal_publication_director": "nom du directeur de la publication",
    "legal_host_name": "raison sociale de l'hébergeur",
    "legal_host_address": "adresse de l'hébergeur",
    "legal_host_contact": "site web ou téléphone de l'hébergeur",
    "legal_support_email": "email du service après-vente",
    "legal_cgv_version_date": "date de mise en vigueur des CGV",
    "legal_privacy_updated_date": "date de dernière mise à jour",
    "legal_delivery_reservation_delay": "délai de réserve, ex. 3 jours ouvrés",
    "legal_withdrawal_regime": (
        "régime de rétractation applicable à la vente à distance en Polynésie "
        "française (À FAIRE VALIDER PAR UN CONSEIL JURIDIQUE)"
    ),
    "legal_mediation_scheme": (
        "dispositif de médiation de la consommation applicable en Polynésie française"
    ),
    "legal_invoice_retention": "durée de conservation, ex. 10 ans",
    "legal_technical_log_retention": "durée, ex. 12 mois",
    "legal_payment_terms": "conditions de règlement",
    "legal_late_penalty_terms": "pénalités de retard",
}

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def get_template(slug: str) -> LegalTemplate | None:
    """The template for ``slug``, or ``None`` when the slug is not a legal page."""
    return next((t for t in LEGAL_TEMPLATES if t.slug == slug), None)


def placeholder(key: str) -> Markup:
    """The marker shown for an empty identity value (HTML, already escaped)."""
    label = _MISSING_LABELS.get(key, key.removeprefix("legal_").replace("_", " "))
    return Markup("<strong>{}</strong>").format(f"{PLACEHOLDER_PREFIX} : {label}]")


def substitute_identity(identity: dict[str, str]) -> dict[str, Markup]:
    """Every ``legal_*`` key → its escaped value, or the placeholder marker."""
    return {
        key: escape(identity[key].strip())
        if identity.get(key, "").strip()
        else placeholder(key)
        for key in LEGAL_SETTING_KEYS
    }


def render_legal_template(
    slug: str, identity: dict[str, str], *, lang: str = DEFAULT_LANG
) -> str:
    """The HTML body of the legal page ``slug`` with the identity substituted.

    Raises ``KeyError`` for a slug that is not a legal template.
    """
    if slug not in LEGAL_TEMPLATE_SLUGS:
        raise KeyError(slug)
    template = _env.get_template(f"{lang}/{slug}.html")
    return template.render(
        v=substitute_identity(identity), currency=settings.REFERENCE_CURRENCY
    ).strip()


async def render_legal_template_from_db(session: AsyncSession, slug: str) -> str:
    """``render_legal_template`` with the identity read from ``system_settings``."""
    identity = await load_legal_identity(session)
    return render_legal_template(slug, identity)
