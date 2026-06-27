from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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
from app.features.place.models import Place
from app.features.product.models.currency_rate import CurrencyRate, CurrencyRateSource
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.tax_rate import TaxRate
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.models.status import StatusDefinition, StatusTransition
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


async def initial_data(session: AsyncSession) -> None:
    """Execute initial data."""
    await _seed_payment_statuses(session)
    await _seed_manual_payment_methods(session)
    await _seed_price_groups(session)
    await _seed_tax_rates(session)
    await _seed_currency_rates(session)
    await _seed_france_papeete_import_corridor(session)
    await _seed_shipping_statuses(session)
    await _seed_security_groups(session)
