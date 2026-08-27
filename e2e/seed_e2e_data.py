"""Seed the minimum data an end-to-end checkout journey needs (Q4).

Run inside the api container, after ``alembic upgrade head`` and
``app.initial_data`` (which already seed the payment methods, including the
manual transfer this journey pays with — no real gateway involved).

Idempotent: re-running it reuses whatever already exists, so a developer can
call it repeatedly against a stack they keep alive.

    docker compose exec -T api python -m app.scripts.noop  # (see e2e/README)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from decimal import Decimal

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.core.security import get_password_hash
from app.features.inventory.models.inventory import Inventory
from app.features.product.models.product import Product
from app.features.user.models.address import Address
from app.features.user.models.user import User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed-e2e")

E2E_EMAIL = "e2e-customer@example.com"
E2E_PASSWORD = "e2e-customer-password-123"
E2E_PRODUCT_NAME = "Station de travail E2E"


async def _seed(session: AsyncSession) -> None:
    user = (
        await session.exec(select(User).where(col(User.email) == E2E_EMAIL))
    ).first()
    if user is None:
        user = User(
            email=E2E_EMAIL,
            full_name="Client E2E",
            hashed_password=get_password_hash(E2E_PASSWORD),
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()
        logger.info("user created: %s", E2E_EMAIL)
    else:
        # Keep the password in sync so a re-seed cannot leave the test locked
        # out of an account seeded by an older revision.
        user.hashed_password = get_password_hash(E2E_PASSWORD)
        session.add(user)
        logger.info("user reused: %s", E2E_EMAIL)

    address = (
        await session.exec(select(Address).where(col(Address.user_id) == user.id))
    ).first()
    if address is None:
        session.add(
            Address(
                user_id=user.id,
                street="BP 42",
                city="Papeete",
                postal_code="98713",
                country="PF",
                type="shipping",
                is_validated=True,
            )
        )
        logger.info("address created")

    product = (
        await session.exec(
            select(Product).where(col(Product.name) == E2E_PRODUCT_NAME)
        )
    ).first()
    if product is None:
        product = Product(
            name=E2E_PRODUCT_NAME,
            description="Produit de test du parcours e2e.",
            base_price=Decimal("50000.00"),
            cost_amount=Decimal("30000.00"),
            cost_currency="XPF",
            # The storefront card reads `supplier_quantity`, not the Inventory
            # table: a product without it renders as "Sur commande" with the
            # add-to-cart button disabled, and the journey stops on the
            # catalogue page.
            supplier_quantity=Decimal("50"),
            # The public catalogue filters on is_enriched: a product without it
            # is invisible to the storefront, and the journey would start on an
            # empty page.
            is_enriched=True,
            is_active=True,
            is_admin_active=True,
        )
        session.add(product)
        await session.flush()
        logger.info("product created: %s", E2E_PRODUCT_NAME)

    inventory = (
        await session.exec(
            select(Inventory).where(col(Inventory.product_id) == product.id)
        )
    ).first()
    if inventory is None:
        session.add(
            Inventory(product_id=product.id, quantity=Decimal("50"))
        )
        logger.info("inventory created")
    else:
        # Checkout consumes stock; top it back up so repeated runs keep working.
        inventory.quantity = Decimal("50")
        session.add(inventory)

    # Same for the catalogue-facing quantity, which repeated checkouts drain.
    product.supplier_quantity = Decimal("50")
    session.add(product)

    await session.commit()


async def main() -> None:
    async with AsyncSession(engine) as session:
        await _seed(session)
    logger.info("e2e seed complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 — surface the reason to the runner
        logger.error("e2e seed failed: %s", exc)
        sys.exit(1)
