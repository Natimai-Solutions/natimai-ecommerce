"""Characteristics typed by hand (R9 / T4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    admin_product_specs_form,
    admin_set_product_specs,
)
from app.core.errors import AppError
from app.features.product.models.category import Category
from app.features.product.models.product import PricingMode, Product
from app.features.product.models.product_spec import ProductSpec
from app.features.product.models.spec_definition import SpecDefinition
from app.features.product.services.manual_specs import SpecValueWrite
from app.features.product.services.spec_projection import upsert_product_specs
from app.features.user.models.user import User


def _definition(
    key: str, label: str, type_: str, unit: str | None, cats: list[str]
) -> SpecDefinition:
    return SpecDefinition(
        key=key,
        label_fr=label,
        type=type_,
        unit=unit,
        categories=cats,
        aliases=[label],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_manual_specs_follow_the_category_and_survive_the_projection(
    db_session: AsyncSession,
) -> None:
    admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))
    laptops = Category(name="Ordinateurs portables")
    screens = Category(name="Écrans")
    db_session.add_all([laptops, screens])
    await db_session.flush()
    db_session.add_all(
        [
            _definition("memory_gb", "Mémoire (Go)", "numeric", "GB", ["ordinateur"]),
            _definition("color", "Couleur", "enum", None, []),
            _definition(
                "screen_size_inch", "Taille (pouces)", "numeric", "inch", ["écran"]
            ),
        ]
    )
    other = Product(
        name="Autre",
        supplier_name="x",
        supplier_sku="x-1",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("1"),
        category_id=laptops.id,
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(
        ProductSpec(product_id=other.id, spec_key="color", value_text="black")
    )
    manual = Product(
        name="PC manuel",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("100000"),
        category_id=laptops.id,
        is_supplier_managed=False,
        is_enriched=False,
    )
    db_session.add(manual)
    manual_id, screens_id = manual.id, screens.id
    await db_session.commit()

    # The form offers the specs of the product's category (by the category
    # name — a manual product has no supplier category) plus the generic ones.
    form = await admin_product_specs_form(db_session, admin, product_id=manual_id)
    assert [r.key for r in form.specs] == ["memory_gb", "color"]
    colour = next(r for r in form.specs if r.key == "color")
    assert colour.suggestions == ["black"] and colour.source is None
    # Before any product exists, the chosen category drives the list.
    draft = await admin_product_specs_form(db_session, admin, category_id=screens_id)
    assert [r.key for r in draft.specs] == ["color", "screen_size_inch"]

    saved = await admin_set_product_specs(
        db_session,
        admin,
        manual_id,
        [
            SpecValueWrite(key="memory_gb", value=" 16 "),
            SpecValueWrite(key="color", value="Gris Sidéral"),
        ],
    )
    by_key = {r.key: r for r in saved.specs}
    assert (
        by_key["memory_gb"].value_numeric == Decimal("16")
        and by_key["memory_gb"].source == "manual"
    )
    assert by_key["memory_gb"].unit == "GB"
    assert by_key["color"].value_text == "gris sidéral"  # same normalisation as Icecat

    with pytest.raises(AppError) as bad:
        await admin_set_product_specs(
            db_session,
            admin,
            manual_id,
            [SpecValueWrite(key="memory_gb", value="seize")],
        )
    assert bad.value.code == "product.spec.invalid"
    with pytest.raises(AppError) as unknown:
        await admin_set_product_specs(
            db_session, admin, manual_id, [SpecValueWrite(key="weight_kg", value="2")]
        )
    assert unknown.value.code == "product.spec.unknown"

    # The Icecat projection leaves the manual rows alone.
    manual = cast(Product, await db_session.get(Product, manual_id))
    manual.technical_specifications = [
        {"name": "Mémoire (Go)", "value": "8 GB"},
        {"name": "Couleur", "value": "Noir"},
    ]
    manual.supplier_category = "Ordinateur"
    db_session.add(manual)
    await db_session.flush()
    await upsert_product_specs(db_session, manual)
    await db_session.commit()
    rows = {
        r.spec_key: r
        for r in (
            await db_session.exec(
                select(ProductSpec).where(ProductSpec.product_id == manual_id)
            )
        ).all()
    }
    assert rows["memory_gb"].value_numeric == Decimal("16")
    assert rows["color"].value_text == "gris sidéral"

    # Blank removes the row.
    cleared = await admin_set_product_specs(
        db_session, admin, manual_id, [SpecValueWrite(key="color", value="")]
    )
    assert next(r for r in cleared.specs if r.key == "color").source is None


@pytest.mark.asyncio
async def test_definitions_scoped_by_shop_category_id(
    db_session: AsyncSession,
) -> None:
    """A definition attached to a shop category (``category_ids``) applies to
    that category's products — form and Icecat projection alike — whatever
    the supplier category says, and follows a category merge."""
    from app.api.routes.admin_categories import MergeBody, merge_category
    from app.features.product.services.spec_projection import (
        _spec_applies_to_category,
    )

    admin = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))
    screens = Category(name="Écrans")
    monitors = Category(name="Moniteurs")
    laptops = Category(name="Ordinateurs portables")
    db_session.add_all([screens, monitors, laptops])
    await db_session.flush()
    screens_id, monitors_id, laptops_id = screens.id, monitors.id, laptops.id
    scoped = _definition("screen_size_inch", "Taille (pouces)", "numeric", "inch", [])
    scoped.category_ids = [str(screens_id)]
    db_session.add_all(
        [
            scoped,
            _definition("memory_gb", "Mémoire (Go)", "numeric", "GB", ["ordinateur"]),
            _definition("color", "Couleur", "enum", None, []),
        ]
    )
    screen = Product(
        name="Écran 27",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("50000"),
        category_id=screens_id,
        supplier_category="Displays",  # no keyword matches it
        technical_specifications=[
            {"name": "Taille (pouces)", "value": '27"'},
            {"name": "Mémoire (Go)", "value": "8 GB"},
        ],
    )
    db_session.add(screen)
    await db_session.flush()
    screen_id = screen.id
    await db_session.commit()

    # Pure matching rules.
    assert _spec_applies_to_category(
        {"category_ids": [str(screens_id)]}, "", screens_id
    )
    assert not _spec_applies_to_category(
        {"category_ids": [str(screens_id)]}, "", laptops_id
    )
    assert not _spec_applies_to_category(
        {"category_ids": [str(screens_id)], "categories": ["ordinateur"]},
        "Displays",
        laptops_id,
    )
    assert _spec_applies_to_category(
        {"category_ids": [str(screens_id)], "categories": ["ordinateur"]},
        "Ordinateur portable",
        laptops_id,
    )
    assert _spec_applies_to_category({}, "", None)

    # The form offers the scoped spec for the screen (by id), not the laptop one.
    form = await admin_product_specs_form(db_session, admin, product_id=screen_id)
    assert {r.key for r in form.specs} == {"screen_size_inch", "color"}
    # The laptop category still gets « memory_gb » through its keyword.
    draft = await admin_product_specs_form(db_session, admin, category_id=laptops_id)
    assert {r.key for r in draft.specs} == {"memory_gb", "color"}

    # The Icecat projection keeps the scoped spec and drops the foreign one.
    screen = cast(Product, await db_session.get(Product, screen_id))
    await upsert_product_specs(db_session, screen)
    await db_session.commit()
    keys = {
        r.spec_key
        for r in (
            await db_session.exec(
                select(ProductSpec).where(ProductSpec.product_id == screen_id)
            )
        ).all()
    }
    assert keys == {"screen_size_inch"}

    # Merging « Écrans » into « Moniteurs » moves the definition along.
    admin_row = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    db_session.add(admin_row)
    await db_session.flush()
    await merge_category(
        screens_id, MergeBody(target_id=monitors_id), db_session, cast(Any, admin_row)
    )
    moved = (
        await db_session.exec(
            select(SpecDefinition).where(SpecDefinition.key == "screen_size_inch")
        )
    ).one()
    assert moved.category_ids == [str(monitors_id)]
    form = await admin_product_specs_form(db_session, admin, category_id=monitors_id)
    assert {r.key for r in form.specs} == {"screen_size_inch", "color"}
