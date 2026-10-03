"""Demo catalogue, loaded on purpose and removable (R8 / confort, 03/10/2026).

A sales demo or a fresh environment needs a shop that looks alive: a few
categories, a dozen products (new, refurbished, on demand, a parent with two
variants), a hero, two banners and the « Comment ça marche ? » page. This
script loads them from a JSON fixture — never at start-up, never from the
admin: the operator runs it, knowing what it does.

    docker compose exec -T api python -m app.scripts.seed_demo            # load
    docker compose exec -T api python -m app.scripts.seed_demo --purge    # remove
    make seed-demo / make purge-demo

Idempotent: every demo row carries the fixture's marker (``DEMO-`` SKUs,
titles of the home blocks, slugs of the pages); a second run updates the rows
it created, ``--purge`` deletes them and nothing else. Refused in
``ENVIRONMENT=production`` unless ``--allow-production`` is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import update as sa_update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.datetimes import utcnow
from app.core.db import engine
from app.core.logging_config import configure_logging
from app.features.cart.models.cart import CartItem
from app.features.content.models import ContentPage, HomepageBlock
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.models.stock_movement import InventoryStockMovement
from app.features.order.models.order_line import OrderLine
from app.features.product.models.category import Category
from app.features.product.models.price_history import ProductPriceEntry
from app.features.product.models.product import (
    AvailabilityMode,
    PricingMode,
    Product,
    ProductCondition,
)
from app.features.product.models.product_group_price import ProductGroupPrice
from app.features.product.models.product_link import ProductLink
from app.features.product.models.product_spec import ProductSpec
from app.features.product.models.product_view import ProductViewDaily
from app.features.product.models.stock_alert import StockAlert
from app.features.user.models.review import Review
from app.features.user.models.wishlist import WishlistItem

logger = logging.getLogger("seed-demo")

DEFAULT_FIXTURE = Path(__file__).resolve().parents[1] / "demo" / "catalogue_demo.json"


def load_fixture(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "natimai-demo/1":
        raise SystemExit(f"{path}: format inconnu {data.get('format')!r}")
    return data


async def _category(session: AsyncSession, spec: dict[str, Any]) -> Category:
    row = (
        await session.exec(select(Category).where(col(Category.name) == spec["name"]))
    ).first()
    if row is None:
        row = Category(name=spec["name"])
        logger.info("category created: %s", spec["name"])
    row.description = spec.get("description")
    row.image_url = spec.get("image_url")
    if spec.get("customs_rate_pct") is not None:
        row.default_customs_rate_pct = Decimal(str(spec["customs_rate_pct"]))
    row.is_active = True
    row.is_admin_active = True
    session.add(row)
    await session.flush()
    return row


async def _product(
    session: AsyncSession,
    spec: dict[str, Any],
    *,
    categories: dict[str, Category],
    parents: dict[str, Product],
) -> Product:
    row = (
        await session.exec(
            select(Product).where(col(Product.supplier_sku) == spec["sku"])
        )
    ).first()
    created = row is None
    if row is None:
        row = Product(name=spec["name"], supplier_sku=spec["sku"])
    row.name = spec["name"]
    row.description = spec.get("description") or None
    row.long_description = spec.get("long_description") or None
    row.manufacturer = spec.get("manufacturer")
    row.ean = spec.get("ean")
    row.vendor_part_number = spec["sku"]
    row.pricing_mode = PricingMode.FIXED
    row.base_price = Decimal(str(spec["base_price"]))
    row.cost_amount = Decimal(str(spec.get("cost_amount") or 0))
    row.cost_currency = settings.REFERENCE_CURRENCY
    row.weight = float(spec["weight"])
    row.image_url = spec.get("image_url")
    row.features = list(spec.get("features") or [])
    row.category_id = categories[spec["category"]].id
    row.condition = ProductCondition(spec.get("condition", "new"))
    row.condition_grade = spec.get("condition_grade")
    row.battery_health_pct = spec.get("battery_health_pct")
    row.warranty_months = spec.get("warranty_months")
    row.availability_mode = AvailabilityMode(spec.get("availability_mode", "stock"))
    row.has_variants = bool(spec.get("has_variants"))
    row.is_featured = bool(spec.get("is_featured"))
    row.is_enriched = True
    row.is_draft = False
    row.is_active = True
    row.is_admin_active = True
    row.supplier_quantity = Decimal("0")  # the stock is ours, in Inventory
    parent_sku = spec.get("parent_sku")
    if parent_sku:
        row.parent_product_id = parents[parent_sku].id
        row.variant_options = dict(spec.get("variant_options") or {})
        row.price_extra = Decimal(str(spec.get("price_extra") or 0))
    session.add(row)
    await session.flush()
    quantity = Decimal(str(spec.get("quantity", 0)))
    inventory = (
        await session.exec(
            select(Inventory).where(
                col(Inventory.product_id) == row.id, col(Inventory.place_id).is_(None)
            )
        )
    ).first()
    if inventory is None:
        inventory = Inventory(product_id=row.id, quantity=quantity)
    else:
        inventory.quantity = quantity
    session.add(inventory)
    logger.info("product %s: %s", "created" if created else "updated", spec["name"])
    return row


async def _homepage(session: AsyncSession, blocks: list[dict[str, Any]]) -> None:
    for spec in blocks:
        row = (
            await session.exec(
                select(HomepageBlock).where(
                    col(HomepageBlock.kind) == spec["kind"],
                    col(HomepageBlock.title) == spec["title"],
                )
            )
        ).first()
        if row is None:
            row = HomepageBlock(
                kind=spec["kind"], title=spec["title"], created_at=utcnow()
            )
            logger.info("home block created: %s", spec["title"])
        for field in (
            "subtitle",
            "cta_label",
            "cta_link",
            "image_url",
            "alt",
            "position",
        ):
            if field in spec:
                setattr(row, field, spec[field])
        row.is_published = bool(spec.get("is_published", True))
        row.is_active = True
        session.add(row)


async def _pages(session: AsyncSession, pages: list[dict[str, Any]]) -> None:
    for spec in pages:
        row = (
            await session.exec(
                select(ContentPage).where(col(ContentPage.slug) == spec["slug"])
            )
        ).first()
        if row is None:
            row = ContentPage(slug=spec["slug"], title=spec["title"])
            logger.info("page created: %s", spec["slug"])
        row.title = spec["title"]
        row.body_html = spec.get("body_html", "")
        row.is_published = bool(spec.get("is_published", True))
        session.add(row)


async def seed(session: AsyncSession, fixture: dict[str, Any]) -> list[uuid.UUID]:
    categories = {
        spec["name"]: await _category(session, spec) for spec in fixture["categories"]
    }
    parents: dict[str, Product] = {}
    product_ids: list[uuid.UUID] = []
    # Parents first: a variant points at its parent's id.
    ordered = sorted(fixture["products"], key=lambda s: bool(s.get("parent_sku")))
    for spec in ordered:
        row = await _product(session, spec, categories=categories, parents=parents)
        product_ids.append(row.id)
        if spec.get("has_variants"):
            parents[spec["sku"]] = row
    await _homepage(session, fixture.get("homepage", []))
    await _pages(session, fixture.get("pages", []))
    await session.commit()
    return product_ids


async def purge(session: AsyncSession, fixture: dict[str, Any]) -> None:
    """Remove what the seed created. A demo product that got ordered in the
    meantime cannot go (the order and its invoice point at it): it is
    deactivated instead, so the storefront no longer shows it."""
    marker = fixture["marker"]
    ids = list(
        (
            await session.exec(
                select(Product.id).where(col(Product.supplier_sku).like(f"{marker}%"))
            )
        ).all()
    )
    ordered = (
        set(
            (
                await session.exec(
                    select(OrderLine.product_id).where(
                        col(OrderLine.product_id).in_(ids)
                    )
                )
            ).all()
        )
        if ids
        else set()
    )
    removable = [pid for pid in ids if pid not in ordered]
    if ordered:
        await session.execute(
            sa_update(Product)
            .where(col(Product.id).in_(list(ordered)))
            .values(is_active=False, is_admin_active=False)
        )
        logger.info(
            "%s demo products were ordered: deactivated, not deleted", len(ordered)
        )
    if removable:
        # Everything that only exists because of the product.
        for model, column in (
            (Inventory, Inventory.product_id),
            (InventoryStockMovement, InventoryStockMovement.product_id),
            (ProductPriceEntry, ProductPriceEntry.product_id),
            (ProductSpec, ProductSpec.product_id),
            (ProductGroupPrice, ProductGroupPrice.product_id),
            (ProductViewDaily, ProductViewDaily.product_id),
            (StockAlert, StockAlert.product_id),
            (WishlistItem, WishlistItem.product_id),
            (CartItem, CartItem.product_id),
            (Review, Review.product_id),
            (ProductLink, ProductLink.product_id),
            (ProductLink, ProductLink.linked_product_id),
        ):
            await session.execute(sa_delete(model).where(col(column).in_(removable)))
        # Variants before their parent.
        await session.execute(
            sa_delete(Product).where(
                col(Product.id).in_(removable),
                col(Product.parent_product_id).is_not(None),
            )
        )
        await session.execute(sa_delete(Product).where(col(Product.id).in_(removable)))
    for spec in fixture.get("homepage", []):
        await session.execute(
            sa_delete(HomepageBlock).where(
                col(HomepageBlock.kind) == spec["kind"],
                col(HomepageBlock.title) == spec["title"],
            )
        )
    for spec in fixture.get("pages", []):
        await session.execute(
            sa_delete(ContentPage).where(col(ContentPage.slug) == spec["slug"])
        )
    for spec in fixture["categories"]:
        category = (
            await session.exec(
                select(Category).where(col(Category.name) == spec["name"])
            )
        ).first()
        if category is None:
            continue
        remaining = (
            await session.exec(
                select(Product.id)
                .where(col(Product.category_id) == category.id)
                .limit(1)
            )
        ).first()
        if remaining is None:
            await session.delete(category)
    await session.commit()
    logger.info("demo data removed (%s products deleted)", len(removable))


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--purge", action="store_true", help="remove the demo data")
    parser.add_argument(
        "--allow-production", action="store_true", help="run even in production"
    )
    args = parser.parse_args(argv)
    if settings.ENVIRONMENT == "production" and not args.allow_production:
        logger.error("ENVIRONMENT=production : refusé sans --allow-production")
        return 2
    fixture = load_fixture(args.file)
    async with AsyncSession(engine) as session:
        if args.purge:
            await purge(session, fixture)
            return 0
        product_ids = await seed(session, fixture)
        # Sale prices are materialised by the pricing service, like any import.
        from app.tasks.pricing_tasks import refresh_sale_prices

        stats = await refresh_sale_prices(
            session, product_ids=product_ids, reason="demo_seed"
        )
        logger.info(
            "demo seed complete: %s products, prices %s", len(product_ids), stats
        )
    return 0


if __name__ == "__main__":
    configure_logging(service="seed-demo")
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:  # noqa: BLE001 — surface the reason to the operator
        logger.error("demo seed failed: %s", exc)
        sys.exit(1)
