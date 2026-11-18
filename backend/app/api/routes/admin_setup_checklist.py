"""Admin start-up checklist: what the shop still needs before its first order.

Each item is computed from the data, never ticked by hand: it is done when
the shop is actually ready on that point. ``check`` marks a value that is
legitimate at zero only when chosen on purpose (insurance rate, customs
declaration fees): the admin confirms it by looking, the item stays visible.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import col, or_

from app.api.deps import CurrentSuperUser, SessionDep
from app.api.routes.admin_dashboard import _count
from app.core import runtime_settings
from app.features.payment.models.payment_method import PaymentMethod
from app.features.place.models import Place
from app.features.product.models.product import PricingMode, Product
from app.features.product.services.publication import (
    content_ready_condition,
    customs_rate_condition,
    weight_condition,
)
from app.features.shipping.models.route import ShippingRoute
from app.features.system.legal_identity import (
    load_legal_identity,
    missing_for_invoicing,
)

router = APIRouter(prefix="/admin/setup-checklist", tags=["admin-dashboard"])

ItemStatus = Literal["done", "todo", "check"]


class SetupChecklistItem(BaseModel):
    #: Stable key; the admin translates the label and the hint from it.
    key: str
    status: ItemStatus
    #: How many things are missing (fields, products, places), when it counts.
    count: int = 0
    #: Admin route where the item is settled.
    to: str


class SetupChecklist(BaseModel):
    items: list[SetupChecklistItem]
    done: int
    total: int
    #: Every item is done (``check`` items do not block).
    ready: bool


def _is_zero(value: object) -> bool:
    try:
        return Decimal(str(value or 0)) == 0
    except InvalidOperation:
        return True


@router.get("", response_model=SetupChecklist)
async def get_setup_checklist(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> SetupChecklist:
    """The start-up checklist, computed from the current data."""
    items: list[SetupChecklistItem] = []

    # Legal identity: printed on every invoice, refused when incomplete.
    missing_legal = missing_for_invoicing(await load_legal_identity(session))
    items.append(
        SetupChecklistItem(
            key="legal_identity",
            status="todo" if missing_legal else "done",
            count=len(missing_legal),
            to="/system-settings?category=legal",
        )
    )

    # Where the alerts go (manual payments, failures, amount mismatches).
    support_email = str(await runtime_settings.get("email_support", session) or "")
    items.append(
        SetupChecklistItem(
            key="support_email",
            status="done" if support_email.strip() else "todo",
            to="/system-settings?category=notifications",
        )
    )

    # At least one way to pay.
    active_methods = await _count(
        session,
        PaymentMethod,
        col(PaymentMethod.is_active).is_(True),
        col(PaymentMethod.is_admin_active).is_(True),
    )
    items.append(
        SetupChecklistItem(
            key="payment_methods",
            status="done" if active_methods else "todo",
            to="/payment-eligibility",
        )
    )

    # The catalogue, as the storefront sees it (publication.py): a product
    # with content (enriched, manual, or published as it stands) and not a
    # draft. The customs rate and the weight only block an imported product.
    catalogue = [
        col(Product.is_active).is_(True),
        col(Product.is_admin_active).is_(True),
        col(Product.is_draft).is_(False),
        content_ready_condition(),
    ]
    imported = [*catalogue, col(Product.pricing_mode) == PricingMode.IMPORT.value]
    with_content = await _count(session, Product, *catalogue)
    blocked_customs = await _count(
        session, Product, *imported, ~customs_rate_condition()
    )
    blocked_weight = await _count(session, Product, *imported, ~weight_condition())
    items.append(
        SetupChecklistItem(
            key="catalogue",
            status="done" if with_content else "todo",
            count=with_content,
            to="/products",
        )
    )
    items.append(
        SetupChecklistItem(
            key="customs_rates",
            status="todo" if blocked_customs else "done",
            count=blocked_customs,
            to="/customs-rates",
        )
    )
    items.append(
        SetupChecklistItem(
            key="weights",
            status="todo" if blocked_weight else "done",
            count=blocked_weight,
            to="/products",
        )
    )

    # The import freight is priced on the routes carrying a service level:
    # with none, an imported article's price holds no freight at all, and the
    # checkout skips the import leg as « already in the price » — the freight
    # was billed nowhere, without a word (review of 17/11/2026).
    import_route_on = (
        col(ShippingRoute.is_active).is_(True),
        col(ShippingRoute.service_level).is_not(None),
    )
    imported_count = await _count(session, Product, *imported)
    import_routes_count = await _count(session, ShippingRoute, *import_route_on)
    items.append(
        SetupChecklistItem(
            key="import_routes",
            status="todo" if imported_count and not import_routes_count else "done",
            to="/logistics-routes",
        )
    )
    # Its fixed cost (the forwarder's fee per shipment) is spread per kg over
    # the weight of a departure at its threshold; without that weight it is
    # billed nowhere (decision of 18/11/2026).
    unspread_fixed = await _count(
        session,
        ShippingRoute,
        *import_route_on,
        col(ShippingRoute.base_price) > 0,
        or_(
            col(ShippingRoute.import_fixed_basis_kg).is_(None),
            col(ShippingRoute.import_fixed_basis_kg) <= 0,
        ),
    )
    items.append(
        SetupChecklistItem(
            key="import_fixed_cost",
            status="todo" if unspread_fixed else "done",
            count=unspread_fixed,
            to="/logistics-routes",
        )
    )

    # Zero is legitimate here only when chosen on purpose.
    insurance = await runtime_settings.get("insurance_rate_pct", session)
    items.append(
        SetupChecklistItem(
            key="insurance_rate",
            status="check" if _is_zero(insurance) else "done",
            to="/system-settings?category=pricing",
        )
    )
    unpriced_clearance = await _count(
        session,
        Place,
        col(Place.is_active).is_(True),
        col(Place.customs_clearance).is_(True),
        col(Place.customs_declaration_fee).is_(None),
    )
    items.append(
        SetupChecklistItem(
            key="customs_declaration_fees",
            status="check" if unpriced_clearance else "done",
            count=unpriced_clearance,
            to="/logistics-routes?view=places",
        )
    )

    done = sum(1 for item in items if item.status == "done")
    return SetupChecklist(
        items=items,
        done=done,
        total=len(items),
        ready=all(item.status != "todo" for item in items),
    )
