"""Integration: main warehouse in the database, origin regime, and their effect
on pricing, publication and the customs declaration fee."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import _customs_declaration_fees
from app.features.place.models import Place
from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.product.services.pricing import (
    calculate_sale_price,
    resolve_effective_customs_rate_pct,
)
from app.features.product.services.publication import (
    publication_blockers,
    publication_conditions,
)
from app.features.shipping.models.route import ShippingRoute
from app.features.shipping.services.origin import (
    CUSTOMS_FREE_COUNTRIES_KEY,
    OriginRegime,
    get_main_warehouse,
    resolve_product_origin_regime,
    set_main_warehouse,
)
from app.features.system.models.system_setting import SystemSetting


async def _seed_places(session: AsyncSession) -> tuple[Place, Place, Place]:
    main = Place(
        name="Entrepôt Papeete", type="warehouse", country="PF", is_warehouse=True
    )
    local_supplier = Place(name="Grossiste Tahiti", type="supplier", country="PF")
    foreign_supplier = Place(name="Fournisseur France", type="supplier", country="FR")
    session.add_all([main, local_supplier, foreign_supplier])
    await session.flush()
    return main, local_supplier, foreign_supplier


def _product(
    supplier_place_id: uuid.UUID | None,
    *,
    customs_rate_pct: Decimal | None = Decimal("20"),
    category_id: uuid.UUID | None = None,
) -> Product:
    return Product(
        name=f"P-{uuid.uuid4().hex[:6]}",
        base_price=Decimal("100"),
        cost_amount=Decimal("100"),
        weight=1.0,
        customs_rate_pct=customs_rate_pct,
        supplier_place_id=supplier_place_id,
        category_id=category_id,
    )


@pytest.mark.asyncio
async def test_main_warehouse_is_flagged_in_the_database(
    db_session: AsyncSession,
) -> None:
    main, _local, _foreign = await _seed_places(db_session)
    other = Place(name="Annexe", type="warehouse", country="PF", is_warehouse=True)
    db_session.add(other)
    await db_session.flush()
    main_id, other_id = main.id, other.id

    # Nothing flagged yet → fallback (first warehouse by name): "Annexe".
    assert (await get_main_warehouse(db_session)).id == other_id  # type: ignore[union-attr]

    await set_main_warehouse(db_session, main_id)
    await db_session.commit()
    assert (await get_main_warehouse(db_session)).id == main_id  # type: ignore[union-attr]

    # Flagging another one unflags the first: exactly one main warehouse.
    await set_main_warehouse(db_session, other_id)
    await db_session.commit()
    flagged = (
        await db_session.exec(select(Place).where(Place.is_main_warehouse.is_(True)))  # type: ignore[attr-defined]
    ).all()
    assert [p.id for p in flagged] == [other_id]

    # The partial unique index refuses a second flag written by hand.
    sneaky = await db_session.get(Place, main_id)
    assert sneaky is not None
    sneaky.is_main_warehouse = True
    db_session.add(sneaky)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()

    unknown = uuid.uuid4()
    with pytest.raises(LookupError):
        await set_main_warehouse(db_session, unknown)


@pytest.mark.asyncio
async def test_product_regime_follows_country_setting_and_override(
    db_session: AsyncSession,
) -> None:
    main, local_supplier, foreign_supplier = await _seed_places(db_session)
    await set_main_warehouse(db_session, main.id)
    local_product = _product(local_supplier.id)
    foreign_product = _product(foreign_supplier.id)
    orphan_product = _product(None)
    db_session.add_all([local_product, foreign_product, orphan_product])
    await db_session.flush()

    assert (
        await resolve_product_origin_regime(db_session, local_product)
        is OriginRegime.DOMESTIC
    )
    assert (
        await resolve_product_origin_regime(db_session, foreign_product)
        is OriginRegime.IMPORT
    )
    assert (
        await resolve_product_origin_regime(db_session, orphan_product)
        is OriginRegime.UNKNOWN
    )

    # France listed as customs-free → its suppliers become domestic.
    db_session.add(SystemSetting(key=CUSTOMS_FREE_COUNTRIES_KEY, value="FR"))
    await db_session.flush()
    assert (
        await resolve_product_origin_regime(db_session, foreign_product)
        is OriginRegime.DOMESTIC
    )

    # An explicit 'import' on the place wins over the country list.
    foreign_supplier.customs_regime = "import"
    db_session.add(foreign_supplier)
    await db_session.flush()
    assert (
        await resolve_product_origin_regime(db_session, foreign_product)
        is OriginRegime.IMPORT
    )


@pytest.mark.asyncio
async def test_domestic_origin_prices_without_customs_or_freight(
    db_session: AsyncSession,
) -> None:
    main, local_supplier, foreign_supplier = await _seed_places(db_session)
    await set_main_warehouse(db_session, main.id)
    import_route = ShippingRoute(
        from_place_id=foreign_supplier.id,
        to_place_id=main.id,
        name="FR → PF",
        mode="air",
        price_per_kg=Decimal("10"),
    )
    local_product = _product(local_supplier.id)
    foreign_product = _product(foreign_supplier.id)
    db_session.add_all([import_route, local_product, foreign_product])
    await db_session.flush()

    # Same cost, same 20 % customs rate on the product: only the import one
    # pays freight (10 × 1 kg) and customs. No price group seeded → the
    # default 30 % margin applies to both; no tax rate → 0 %.
    local_price = await calculate_sale_price(
        db_session, local_product, import_route=import_route
    )
    foreign_price = await calculate_sale_price(
        db_session, foreign_product, import_route=import_route
    )
    assert local_price == Decimal("130.00")  # 100 × 1.30
    assert foreign_price == Decimal("171.60")  # (100 + 10) × 1.20 × 1.30

    assert await resolve_effective_customs_rate_pct(db_session, local_product) == 0
    assert await resolve_effective_customs_rate_pct(db_session, foreign_product) == 20


@pytest.mark.asyncio
async def test_domestic_origin_publishes_without_a_customs_rate(
    db_session: AsyncSession,
) -> None:
    main, local_supplier, foreign_supplier = await _seed_places(db_session)
    await set_main_warehouse(db_session, main.id)
    category = Category(name=f"Sans taux {uuid.uuid4().hex[:6]}")
    db_session.add(category)
    await db_session.flush()
    local_product = _product(
        local_supplier.id, customs_rate_pct=None, category_id=category.id
    )
    foreign_product = _product(
        foreign_supplier.id, customs_rate_pct=None, category_id=category.id
    )
    db_session.add_all([local_product, foreign_product])
    await db_session.flush()

    # Python-side blockers…
    assert await publication_blockers(db_session, local_product) == []
    assert "customs_rate_unresolved" in await publication_blockers(
        db_session, foreign_product
    )
    # …and the SQL gate used by catalogue listings agree.
    visible = (
        await db_session.exec(select(Product).where(*publication_conditions()))
    ).all()
    assert {p.id for p in visible} == {local_product.id}


@pytest.mark.asyncio
async def test_declaration_fee_only_when_an_item_crosses_customs(
    db_session: AsyncSession,
) -> None:
    main, local_supplier, foreign_supplier = await _seed_places(db_session)
    await set_main_warehouse(db_session, main.id)
    main.customs_clearance = True
    main.customs_declaration_fee = Decimal("1500")
    db_session.add(main)
    db_session.add(
        ShippingRoute(
            from_place_id=foreign_supplier.id,
            to_place_id=main.id,
            name="FR → PF",
            mode="sea",
        )
    )
    local_product = _product(local_supplier.id)
    foreign_product = _product(foreign_supplier.id)
    orphan_product = _product(None)
    db_session.add_all([local_product, foreign_product, orphan_product])
    await db_session.flush()

    assert await _customs_declaration_fees(db_session, [local_product]) == []
    billed = await _customs_declaration_fees(
        db_session, [local_product, foreign_product]
    )
    assert [fee.amount for fee in billed] == [Decimal("1500")]
    # Unconfigured origin keeps the historical behaviour: billed.
    assert len(await _customs_declaration_fees(db_session, [orphan_product])) == 1
    # No products given (legacy callers): billed as before.
    assert len(await _customs_declaration_fees(db_session)) == 1
