from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.content.crud import crud_content_page
from app.features.content.models import ContentPageCreate
from app.features.departure.services import SOCIAL_WEBHOOK_SETTING_KEY
from app.features.order.services.status import (
    ALL_ORDER_STATUSES,
    get_or_create_order_status,
)
from app.features.payment.crud.payment_method import crud_payment_method
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
)
from app.features.payment.models.payment_status import PaymentStatusCreate
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_DOCUMENT_REQUIRED,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_UNDER_REVIEW,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)
from app.features.place.models import Place, PlacePostalCode
from app.features.product.models.currency_rate import CurrencyRate, CurrencyRateSource
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.tax_rate import TaxRate
from app.features.shipping.models.carrier import Carrier
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.status import StatusDefinition, StatusTransition
from app.features.shipping.services.origin import (
    CUSTOMS_FREE_COUNTRIES_DESCRIPTION,
    CUSTOMS_FREE_COUNTRIES_KEY,
)
from app.features.system.legal_identity import LEGAL_SETTINGS, seed_value_for
from app.features.system.models.system_setting import SystemSetting
from app.features.user.models.group import Group
from app.features.user.models.group_security import GroupSecurity

DEFAULT_PAYMENT_STATUSES: tuple[tuple[str, str], ...] = (
    ("Pending", "Payment initiated, awaiting provider action"),
    (MANUAL_STATUS_AWAITING_VALIDATION, "Awaiting manual admin validation"),
    (DOCUMENT_STATUS_DOCUMENT_REQUIRED, "Waiting for document upload from client"),
    (DOCUMENT_STATUS_DOCUMENT_UPLOADED, "Document uploaded, awaiting AV scan"),
    (DOCUMENT_STATUS_UNDER_REVIEW, "Document under admin review"),
    (MANUAL_STATUS_COMPLETED, "Payment confirmed and captured"),
    (MANUAL_STATUS_FAILED, "Payment failed or was rejected"),
    ("Authorized", "Card authorised (funds reserved), awaiting capture at shipment"),
    ("Refunded", "Payment fully refunded to the customer"),
    ("PartiallyRefunded", "Payment partially refunded to the customer"),
)


async def _seed_payment_statuses(session: AsyncSession) -> None:
    """Execute seed payment statuses."""
    for name, description in DEFAULT_PAYMENT_STATUSES:
        existing = await crud_payment_status.get_by_name(session, name=name)
        if existing is not None:
            continue
        await crud_payment_status.create_draft(
            session=session,
            data=PaymentStatusCreate(name=name, description=description),
            user=None,
        )


async def _seed_manual_payment_methods(session: AsyncSession) -> None:
    """Execute seed manual payment methods."""
    methods = (
        {
            "name": "Carte bancaire",
            "description": "Paiement par carte bancaire (CB) via PayZen SmartForm.",
            "provider_code": "payzen",
            "sort_order": 10,
            "requires_admin_validation": False,
            "requires_document_upload": False,
        },
        {
            "name": "Chèque",
            "description": "Paiement par chèque, validé manuellement à réception.",
            "provider_code": "manual_check",
            "sort_order": 80,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Virement bancaire",
            "description": "Paiement par virement bancaire, validé manuellement à réception.",
            "provider_code": "manual_transfer",
            "sort_order": 90,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Bon de commande",
            "description": (
                "Paiement sur bon de commande signé. Le client téléverse "
                "son BC et notre équipe valide la commande après vérification."
            ),
            "provider_code": "po_public",
            "sort_order": 100,
            "requires_admin_validation": True,
            "requires_document_upload": True,
        },
    )

    for spec in methods:
        statement = select(PaymentMethod).where(
            PaymentMethod.provider_code == spec["provider_code"]
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue

        await crud_payment_method.create_draft(
            session=session,
            data=PaymentMethodCreate(
                name=spec["name"],
                description=spec["description"],
                provider_code=spec["provider_code"],
                requires_admin_validation=spec["requires_admin_validation"],
                requires_document_upload=spec["requires_document_upload"],
                sort_order=spec["sort_order"],
                fee=Decimal("0.00"),
            ),
            user=None,
        )


async def _seed_price_groups(session: AsyncSession) -> None:
    """Seed default price groups used by runtime pricing."""
    groups = (
        {
            "code": "PARTICULIER",
            "label": "Particulier",
            "margin_rate_pct": Decimal("30.00"),
            "default": True,
            "requires_validation": False,
        },
        {
            "code": "PROFESSIONNEL",
            "label": "Professionnel",
            "margin_rate_pct": Decimal("25.00"),
            "default": False,
            "requires_validation": True,
        },
        {
            "code": "REVENDEUR",
            "label": "Revendeur",
            "margin_rate_pct": Decimal("12.00"),
            "default": False,
            "requires_validation": True,
        },
        {
            "code": "PUBLIC",
            "label": "Public / Etablissements",
            "margin_rate_pct": Decimal("18.00"),
            "default": False,
            "requires_validation": True,
        },
    )

    for group in groups:
        statement = select(PriceGroup).where(PriceGroup.code == group["code"])
        result = await session.exec(statement)
        existing = result.first()
        if existing is not None:
            continue
        session.add(PriceGroup.model_validate(group))


async def _seed_carriers(session: AsyncSession) -> None:
    """Seed common carriers with a tracking-URL template ({ref} placeholder).

    URLs are best-effort defaults — an admin can edit/complete them.
    """
    carriers = (
        {
            "name": "DHL",
            "code": "dhl",
            "tracking_url_template": "https://www.dhl.com/track?tracking-id={ref}",
        },
        {
            "name": "Colissimo",
            "code": "colissimo",
            "tracking_url_template": "https://www.laposte.fr/outils/suivre-vos-envois?code={ref}",
        },
        {
            "name": "Chronopost",
            "code": "chronopost",
            "tracking_url_template": "https://www.chronopost.fr/tracking-no-cms/suivi-page?listeNumerosLT={ref}",
        },
        {
            "name": "OPT (Fenua Post)",
            "code": "opt",
            "tracking_url_template": None,
        },
    )
    for carrier in carriers:
        statement = select(Carrier).where(Carrier.code == carrier["code"])
        result = await session.exec(statement)
        if result.first() is not None:
            continue
        session.add(Carrier.model_validate(carrier))


async def _seed_tax_rates(session: AsyncSession) -> None:
    """Seed baseline PF tax rates used by pricing resolution."""
    rates = (
        {
            "code": "TGC_NORMAL",
            "label": "TGC normal",
            "rate_pct": Decimal("16.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
        {
            "code": "TGC_REDUIT",
            "label": "TGC reduit",
            "rate_pct": Decimal("5.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
        {
            "code": "TGC_EXONERE",
            "label": "TGC exonere",
            "rate_pct": Decimal("0.00"),
            "territory_code": "PF",
            "valid_from": date.today(),
            "valid_until": None,
        },
    )

    for rate in rates:
        statement = select(TaxRate).where(
            TaxRate.code == rate["code"],
            TaxRate.territory_code == rate["territory_code"],
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue
        session.add(TaxRate.model_validate(rate))


async def _seed_currency_rates(session: AsyncSession) -> None:
    """Seed baseline FX rates used by pricing conversion (cost → reference currency)."""
    rates = (
        {
            "currency_code": "EUR",
            "rate_to_reference": Decimal("119.332"),
        },
        {
            "currency_code": "USD",
            "rate_to_reference": Decimal("100.000"),
        },
    )

    for rate in rates:
        statement = select(CurrencyRate).where(
            CurrencyRate.currency_code == rate["currency_code"],
            CurrencyRate.is_active == True,  # noqa: E712
            CurrencyRate.valid_until == None,  # noqa: E711
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue
        session.add(
            CurrencyRate(
                currency_code=rate["currency_code"],
                rate_to_reference=rate["rate_to_reference"],
                valid_from=date.today(),
                valid_until=None,
                source=CurrencyRateSource.manual,
                is_active=True,
                is_admin_active=True,
            )
        )


async def _seed_france_papeete_import_corridor(session: AsyncSession) -> None:
    """Seed the France → Papeete import corridor (Phase 1 — single corridor).

    Creates two places and two import routes (rapide/avion + economique/bateau)
    with indicative Phase-1 tariffs. Rates can be updated from the admin UI.
    Identified by stable ``code`` / ``service_level`` values for idempotency.
    """
    # --- Origin: suppliers warehouse in France ---
    fr_result = await session.exec(select(Place).where(Place.code == "FR_SUPPLIERS"))
    fr_place = fr_result.first()
    if fr_place is None:
        fr_place = Place(
            name="Entrepôt fournisseurs (France)",
            type="warehouse",
            code="FR_SUPPLIERS",
            country="FR",
            is_warehouse=True,
        )
        session.add(fr_place)

    # --- Destination: Papeete customs warehouse ---
    ppt_result = await session.exec(
        select(Place).where(Place.code == "PPT_CUSTOMS_WAREHOUSE")
    )
    ppt_place = ppt_result.first()
    if ppt_place is None:
        ppt_place = Place(
            name="Entrepôt douanier Papeete",
            type="warehouse",
            code="PPT_CUSTOMS_WAREHOUSE",
            country="PF",
            city="Papeete",
            is_warehouse=True,
            customs_clearance=True,
        )
        session.add(ppt_place)

    # The corridor's destination is the main warehouse — unless the admin has
    # already flagged another place (never override a deliberate choice).
    any_main = await session.exec(
        select(Place).where(col(Place.is_main_warehouse).is_(True))
    )
    if any_main.first() is None:
        ppt_place.is_main_warehouse = True
        session.add(ppt_place)

    # --- Rapide (avion) ---
    air_result = await session.exec(
        select(ShippingRoute).where(ShippingRoute.service_level == "rapide")
    )
    if air_result.first() is None:
        session.add(
            ShippingRoute(
                name="France → Papeete (avion)",
                from_place_id=fr_place.id,
                to_place_id=ppt_place.id,
                mode="air",
                service_level="rapide",
                customer_label="Rapide (avion ~5-7 j)",
                is_default_import=True,
                price_per_kg=Decimal("700.00"),  # indicatif ≈ 5.87 EUR/kg
                base_price=Decimal("0.00"),
                eta_days=7,
                priority=10,
                status_code="active",
                route_metadata={"dim_factor_kg_per_m3": "167"},
            )
        )

    # --- Économique (bateau) ---
    sea_result = await session.exec(
        select(ShippingRoute).where(ShippingRoute.service_level == "economique")
    )
    if sea_result.first() is None:
        session.add(
            ShippingRoute(
                name="France → Papeete (bateau)",
                from_place_id=fr_place.id,
                to_place_id=ppt_place.id,
                mode="sea",
                service_level="economique",
                customer_label="Économique (bateau ~35 j)",
                is_default_import=False,
                price_per_kg=Decimal("180.00"),  # indicatif ≈ 1.51 EUR/kg
                base_price=Decimal("0.00"),
                eta_days=35,
                priority=20,
                status_code="active",
                route_metadata={"dim_factor_kg_per_m3": "1000"},
            )
        )


# French Polynesia geographic zone tree: country → archipelago (region) →
# island. Identified by stable `code` values for idempotency. Postal codes are
# an INDICATIVE starter set (main communes) — verify/complete them from the
# admin (PUT /place/{id}/postal-codes); an unknown postal code simply leaves
# the address without a zone.
_PF_ARCHIPELAGOS: tuple[tuple[str, str], ...] = (
    ("PF_SOCIETE", "Archipel de la Société"),
    ("PF_TUAMOTU", "Archipel des Tuamotu"),
    ("PF_GAMBIER", "Archipel des Gambier"),
    ("PF_MARQUISES", "Archipel des Marquises"),
    ("PF_AUSTRALES", "Archipel des Australes"),
)

# (code, name, archipelago_code, postal_codes)
_PF_ISLANDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "PF_TAHITI",
        "Tahiti",
        "PF_SOCIETE",
        (
            "98701",  # Arue
            "98704",  # Faa'a
            "98709",  # Mahina
            "98711",  # Paea
            "98712",  # Papara
            "98713",  # Papeete
            "98714",  # Papeete
            "98715",  # Papeete
            "98716",  # Pirae
            "98718",  # Punaauia
        ),
    ),
    ("PF_MOOREA", "Moorea", "PF_SOCIETE", ("98728", "98729")),
    ("PF_BORA_BORA", "Bora Bora", "PF_SOCIETE", ("98730",)),
    ("PF_HUAHINE", "Huahine", "PF_SOCIETE", ("98731",)),
    ("PF_RAIATEA", "Raiatea", "PF_SOCIETE", ("98735",)),
    ("PF_TAHAA", "Taha'a", "PF_SOCIETE", ()),
    ("PF_MAUPITI", "Maupiti", "PF_SOCIETE", ()),
    ("PF_RANGIROA", "Rangiroa", "PF_TUAMOTU", ()),
    ("PF_FAKARAVA", "Fakarava", "PF_TUAMOTU", ()),
    ("PF_TIKEHAU", "Tikehau", "PF_TUAMOTU", ()),
    ("PF_HAO", "Hao", "PF_TUAMOTU", ()),
    ("PF_MANGAREVA", "Mangareva", "PF_GAMBIER", ()),
    ("PF_NUKU_HIVA", "Nuku Hiva", "PF_MARQUISES", ("98742",)),
    ("PF_HIVA_OA", "Hiva Oa", "PF_MARQUISES", ("98741",)),
    ("PF_UA_POU", "Ua Pou", "PF_MARQUISES", ()),
    ("PF_RURUTU", "Rurutu", "PF_AUSTRALES", ()),
    ("PF_TUBUAI", "Tubuai", "PF_AUSTRALES", ()),
    ("PF_RAIVAVAE", "Raivavae", "PF_AUSTRALES", ()),
)


async def _get_or_create_place_by_code(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    place_type: str,
    parent_id: Any = None,
) -> Place:
    """Fetch a place by stable code, creating it when missing (idempotent)."""
    result = await session.exec(select(Place).where(Place.code == code))
    place = result.first()
    if place is None:
        place = Place(
            name=name,
            type=place_type,
            code=code,
            country="PF",
            parent_id=parent_id,
        )
        session.add(place)
        await session.flush()
    return place


async def _seed_french_polynesia_geography(session: AsyncSession) -> None:
    """Seed the PF zone tree (pays → archipels → îles) + starter postal codes.

    Granularity stops at the island (municipalities stay free text on the
    address); the postal-code mapping is what deduces the island at address
    entry. Everything is admin-editable afterwards.
    """
    country = await _get_or_create_place_by_code(
        session,
        code="PF_COUNTRY",
        name="Polynésie française",
        place_type="country",
    )

    archipelagos: dict[str, Place] = {}
    for code, name in _PF_ARCHIPELAGOS:
        archipelagos[code] = await _get_or_create_place_by_code(
            session,
            code=code,
            name=name,
            place_type="region",
            parent_id=country.id,
        )

    for code, name, archipelago_code, postal_codes in _PF_ISLANDS:
        island = await _get_or_create_place_by_code(
            session,
            code=code,
            name=name,
            place_type="island",
            parent_id=archipelagos[archipelago_code].id,
        )
        for postal_code in postal_codes:
            existing = await session.exec(
                select(PlacePostalCode).where(
                    PlacePostalCode.country == "PF",
                    PlacePostalCode.postal_code == postal_code,
                )
            )
            if existing.first() is None:
                session.add(
                    PlacePostalCode(
                        place_id=island.id,
                        country="PF",
                        postal_code=postal_code,
                    )
                )


# Canonical logistics status catalog. Codes are shared by every shipping code
# path: checkout creates trackings as `pending`; admin ship/deliver force
# `shipped`/`delivered`; the multi-leg progression uses `in_progress`
# (active leg) and `completed` (intermediate leg done). `completed` and
# `delivered` are terminal.
_SHIPPING_STATUS_DEFINITIONS: tuple[dict[str, Any], ...] = (
    # entity "route_tracking" — a single leg (tronçon) of an order's journey
    {
        "entity": "route_tracking",
        "code": "pending",
        "name": "En attente",
        "sequence_order": 10,
        "ui_color": "grey",
        "ui_icon": "schedule",
    },
    {
        "entity": "route_tracking",
        "code": "in_progress",
        "name": "En cours",
        "sequence_order": 20,
        "ui_color": "blue",
        "ui_icon": "local_shipping",
    },
    {
        "entity": "route_tracking",
        "code": "shipped",
        "name": "Expédiée",
        "sequence_order": 30,
        "ui_color": "indigo",
        "ui_icon": "flight_takeoff",
    },
    {
        "entity": "route_tracking",
        "code": "completed",
        "name": "Tronçon terminé",
        "sequence_order": 40,
        "is_terminal": True,
        "ui_color": "teal",
        "ui_icon": "check",
    },
    {
        "entity": "route_tracking",
        "code": "delivered",
        "name": "Livrée",
        "sequence_order": 50,
        "is_terminal": True,
        "ui_color": "green",
        "ui_icon": "done_all",
    },
    # entity "consolidation" — a grouped shipment over one route
    {
        "entity": "consolidation",
        "code": "pending",
        "name": "En attente",
        "sequence_order": 10,
        "ui_color": "grey",
        "ui_icon": "schedule",
    },
    {
        "entity": "consolidation",
        "code": "shipped",
        "name": "Expédiée",
        "sequence_order": 30,
        "ui_color": "indigo",
        "ui_icon": "flight_takeoff",
    },
    {
        "entity": "consolidation",
        "code": "delivered",
        "name": "Livrée",
        "sequence_order": 50,
        "is_terminal": True,
        "ui_color": "green",
        "ui_icon": "done_all",
    },
)

# Allowed transitions consulted by update_status when force=False (e.g. the
# /shipping/tracking/{id}/update-status route). (entity, from_code, to_code).
_SHIPPING_STATUS_TRANSITIONS: tuple[tuple[str, str, str], ...] = (
    ("route_tracking", "pending", "in_progress"),
    ("route_tracking", "pending", "shipped"),
    ("route_tracking", "in_progress", "shipped"),
    ("route_tracking", "in_progress", "completed"),
    ("route_tracking", "in_progress", "delivered"),
    ("route_tracking", "shipped", "completed"),
    ("route_tracking", "shipped", "delivered"),
    ("consolidation", "pending", "shipped"),
    ("consolidation", "shipped", "delivered"),
)


# Default « Comment ça marche » page: explains the grouped-departure model
# (why the customer pays up front). Seeded once, never overwritten: the owner
# rewrites it in the back-office.
HOW_IT_WORKS_HTML = """<h2>Des commandes groupées, un prix rendu tout compris</h2>
<p>Nous ne stockons pas les produits à l'avance : vos commandes sont regroupées par <strong>départ</strong>. Chaque départ a une date limite de commande, affichée sur le site. À cette date, nous passons une seule commande à nos fournisseurs, les colis voyagent ensemble, sont dédouanés ensemble, puis remis à chacun.</p>
<h3>1. Vous commandez et payez</h3>
<p>Le prix affiché est le prix final en XPF, fret, douane et taxes compris : rien à payer à l'arrivée. Votre paiement à la commande est ce qui rend ce modèle possible sans stock, et donc sans surcoût.</p>
<h3>2. Le départ est clôturé</h3>
<p>À la date limite, la commande fournisseur est passée. Si un article n'est plus disponible, nous vous proposons le report sur le départ suivant, un article équivalent ou le remboursement.</p>
<h3>3. Transport, douane, réception</h3>
<p>Vous êtes prévenu(e) par e-mail à chaque étape : commandée au fournisseur, en transit, en douane, reçue et contrôlée, puis disponible. Comptez 3 à 5 semaines entre la clôture et la remise.</p>
<h3>4. Remise</h3>
<p>Retrait sur place ou livraison, selon le mode choisi à la commande. Les produits reconditionnés sont signalés comme tels, avec leur grade et leur garantie.</p>
"""


async def _seed_social_webhook_setting(session: AsyncSession) -> None:
    """Empty ``social_webhook_url`` so the reminders tab has a row to edit."""
    existing = (
        await session.exec(
            select(SystemSetting).where(SystemSetting.key == SOCIAL_WEBHOOK_SETTING_KEY)
        )
    ).first()
    if existing is not None:
        return
    session.add(
        SystemSetting(
            key=SOCIAL_WEBHOOK_SETTING_KEY,
            value="",
            description=(
                "URL https d'un webhook (Make, Zapier, Buffer…) recevant les rappels "
                "des départs groupés : {text, link, image_url, departure}"
            ),
        )
    )


async def _seed_content_pages(session: AsyncSession) -> None:
    """Seed the « Comment ça marche » page once (idempotent, never overwrites)."""
    if await crud_content_page.get_by_slug(session, "comment-ca-marche") is not None:
        return
    await crud_content_page.create_draft(
        session,
        data=ContentPageCreate(
            slug="comment-ca-marche",
            title="Comment ça marche ?",
            body_html=HOW_IT_WORKS_HTML,
            is_published=True,
        ),
        user=None,
    )


async def _seed_order_statuses(session: AsyncSession) -> None:
    """Every order status by name (idempotent), so the admin select and the
    departure propagation never depend on a status being created on the fly."""
    for name in ALL_ORDER_STATUSES:
        await get_or_create_order_status(session, name)


async def _seed_shipping_statuses(session: AsyncSession) -> None:
    """Seed the logistics status catalog + allowed transitions (idempotent).

    Without these, force=False status updates reject every transition, and the
    multi-leg progression has no `in_progress`/`completed` codes to resolve.
    """
    for spec in _SHIPPING_STATUS_DEFINITIONS:
        existing = await session.exec(
            select(StatusDefinition).where(
                StatusDefinition.entity == spec["entity"],
                StatusDefinition.code == spec["code"],
            )
        )
        if existing.first() is not None:
            continue
        session.add(StatusDefinition.model_validate(spec))

    for entity, from_code, to_code in _SHIPPING_STATUS_TRANSITIONS:
        existing_transition = await session.exec(
            select(StatusTransition).where(
                StatusTransition.entity == entity,
                StatusTransition.from_code == from_code,
                StatusTransition.to_code == to_code,
            )
        )
        if existing_transition.first() is not None:
            continue
        session.add(
            StatusTransition(entity=entity, from_code=from_code, to_code=to_code)
        )


_SECURITY_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "name": "support",
        "description": (
            "Service client — lecture des commandes, paiements et comptes utilisateurs."
        ),
        "group_type": "security",
        "priority": 10,
        "rules": [
            {"table_name": "users", "can_read": True},
            {"table_name": "orders", "can_read": True},
            {"table_name": "order_lines", "can_read": True},
            {"table_name": "payments", "can_read": True},
            {"table_name": "payment_logs", "can_read": True},
        ],
    },
    {
        "name": "logistics_admin",
        "description": (
            "Logistique — gestion des expéditions, suivis et consolidations."
        ),
        "group_type": "security",
        "priority": 20,
        "rules": [
            {
                "table_name": "shipping_route_trackings",
                "can_read": True,
                "can_update": True,
            },
            {
                "table_name": "shipping_route_tracking_consolidations",
                "can_read": True,
                "can_update": True,
            },
            {
                "table_name": "delivery_tasks",
                "can_read": True,
                "can_update": True,
            },
        ],
    },
    {
        "name": "payment_admin",
        "description": (
            "Administration paiements — validation et gestion des paiements clients."
        ),
        "group_type": "security",
        "priority": 30,
        "rules": [
            {
                "table_name": "payments",
                "can_read": True,
                "can_update": True,
            },
            {
                "table_name": "payment_validations",
                "can_read": True,
                "can_update": True,
            },
            {
                "table_name": "payment_attachments",
                "can_read": True,
                "can_update": True,
            },
        ],
    },
)


async def _seed_security_groups(session: AsyncSession) -> None:
    """Seed RBAC security groups and their table-level permissions.

    Idempotent: skips groups/rules that already exist.
    ENABLE_GROUP_PERMISSIONS must be set to True manually in prod
    after verifying that the superuser and existing users still work.
    """
    for spec in _SECURITY_GROUPS:
        existing = await session.exec(select(Group).where(Group.name == spec["name"]))
        group = existing.first()
        if group is None:
            group = Group(
                name=spec["name"],
                description=spec["description"],
                group_type=spec["group_type"],
                priority=spec["priority"],
                is_active=True,
                is_admin_active=True,
            )
            session.add(group)
            await session.flush()

        for rule in spec["rules"]:
            existing_rule = await session.exec(
                select(GroupSecurity).where(
                    GroupSecurity.group_id == group.id,
                    GroupSecurity.table_name == rule["table_name"],
                )
            )
            if existing_rule.first() is not None:
                continue
            session.add(
                GroupSecurity(
                    group_id=group.id,
                    table_name=rule["table_name"],
                    can_read=rule.get("can_read", False),
                    can_create=rule.get("can_create", False),
                    can_update=rule.get("can_update", False),
                    can_delete=rule.get("can_delete", False),
                    is_active=True,
                    is_admin_active=True,
                )
            )


async def _seed_legal_identity_settings(session: AsyncSession) -> None:
    """Créer les clés d'identité légale, vides, pour qu'elles soient éditables.

    Le back-office ne montre que les lignes existantes : sans ce seed, les
    champs n'apparaîtraient nulle part et personne ne saurait qu'ils sont à
    remplir. Les valeurs sont amorcées depuis les réglages ``INVOICE_SELLER_*``
    quand ils existent, pour qu'un déploiement antérieur ne reparte pas de
    zéro.

    Idempotent, et **ne réécrit jamais une valeur déjà saisie** : ce seed
    tourne à chaque déploiement, écraser le texte légal saisi par le
    propriétaire avec la valeur d'une variable d'environnement oubliée serait
    exactement le genre de régression silencieuse à éviter.
    """
    for spec in LEGAL_SETTINGS:
        result = await session.exec(
            select(SystemSetting).where(SystemSetting.key == spec.key)
        )
        existing = result.first()
        if existing is not None:
            # Seule la description est rafraîchie : elle sert d'aide de saisie
            # dans l'écran admin et peut être améliorée d'une version à l'autre.
            if existing.description != spec.description:
                existing.description = spec.description
                session.add(existing)
            continue

        session.add(
            SystemSetting(
                key=spec.key,
                value=seed_value_for(spec),
                description=spec.description,
            )
        )


async def _seed_suppliers(session: AsyncSession) -> None:
    """Seed the historical distributor as a ``suppliers`` row (idempotent).

    Synced products carry ``supplier_name = 'ingram_micro'``: the row keeps
    them attached to a declared supplier. Created with the ``INGRAM_*``
    environment defaults when missing; when present, only a missing origin
    warehouse is filled in (the admin owns the rest from the back-office).
    """
    from app.features.integrations.models.supplier import Supplier, SupplierKind

    origin_result = await session.exec(
        select(Place).where(Place.code == settings.INGRAM_ORIGIN_PLACE_CODE)
    )
    origin = origin_result.first()

    result = await session.exec(select(Supplier).where(Supplier.code == "ingram_micro"))
    supplier = result.first()
    if supplier is None:
        session.add(
            Supplier(
                code="ingram_micro",
                name="Ingram Micro",
                kind=SupplierKind.API,
                adapter_key="ingram_micro",
                origin_place_id=origin.id if origin is not None else None,
                is_domestic=False,
                sync_enabled=bool(settings.INGRAM_SYNC_ENABLED),
                sync_interval_hours=int(settings.INGRAM_SYNC_INTERVAL_HOURS),
                default_categories=list(settings.INGRAM_SYNC_CATEGORIES),
                settings={
                    "environment": settings.INGRAM_ENVIRONMENT,
                    "country_code": settings.INGRAM_COUNTRY_CODE,
                },
            )
        )
    elif supplier.origin_place_id is None and origin is not None:
        supplier.origin_place_id = origin.id
        session.add(supplier)


async def _seed_customs_free_countries_setting(session: AsyncSession) -> None:
    """Create the (empty) customs-free countries key so it is editable in admin."""
    result = await session.exec(
        select(SystemSetting).where(SystemSetting.key == CUSTOMS_FREE_COUNTRIES_KEY)
    )
    existing = result.first()
    if existing is not None:
        if existing.description != CUSTOMS_FREE_COUNTRIES_DESCRIPTION:
            existing.description = CUSTOMS_FREE_COUNTRIES_DESCRIPTION
            session.add(existing)
        return
    session.add(
        SystemSetting(
            key=CUSTOMS_FREE_COUNTRIES_KEY,
            value="",
            description=CUSTOMS_FREE_COUNTRIES_DESCRIPTION,
        )
    )


async def initial_data(session: AsyncSession) -> None:
    """Execute initial data."""
    await _seed_payment_statuses(session)
    await _seed_manual_payment_methods(session)
    await _seed_price_groups(session)
    await _seed_carriers(session)
    await _seed_tax_rates(session)
    await _seed_currency_rates(session)
    # Territory-specific starter data: skipped for a classic shop
    # (SEED_FRENCH_POLYNESIA_LOGISTICS=false), which only needs carriers,
    # statuses and its own warehouse → customer routes.
    if settings.SEED_FRENCH_POLYNESIA_LOGISTICS:
        await _seed_france_papeete_import_corridor(session)
        await _seed_french_polynesia_geography(session)
    # The historical distributor is not territory-specific: always declared
    # (its origin warehouse is filled in only when the corridor was seeded).
    await _seed_suppliers(session)
    await _seed_shipping_statuses(session)
    await _seed_order_statuses(session)
    await _seed_content_pages(session)
    await _seed_social_webhook_setting(session)
    await _seed_security_groups(session)
    await _seed_legal_identity_settings(session)
    await _seed_customs_free_countries_setting(session)
