"""Remises et coupons (Q3) — ``discount/crud.py`` contre une vraie base.

Le module était couvert à 19 % : les règles de validité d'un coupon (dates,
plafond d'usage, type) n'étaient testées nulle part alors qu'elles décident
d'une réduction sur le total d'une commande.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.discount.crud import crud_discount
from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.product.models.category import Category
from app.features.product.models.product import Product


def _discount(**overrides: Any) -> Discount:
    base: dict[str, Any] = {
        "name": "Remise",
        "discount_type": DiscountType.COUPON,
        "code": f"CODE-{uuid.uuid4().hex[:6]}",
        "percentage": Decimal("10.00"),
        "target": DiscountTarget.ORDER,
        "is_active": True,
    }
    base.update(overrides)
    return Discount(**base)


def _hours(delta: int) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        hours=delta
    )


@pytest.mark.asyncio
async def test_get_by_code_only_returns_active_coupons(
    db_session: AsyncSession,
) -> None:
    """Un code de promotion automatique ou un coupon désactivé ne doivent pas
    être saisissables au panier."""
    coupon = _discount(code="OK10")
    promo = _discount(code="PROMO", discount_type=DiscountType.PROMOTION)
    disabled = _discount(code="OFF", is_active=False)
    db_session.add_all([coupon, promo, disabled])
    await db_session.flush()
    coupon_id = coupon.id

    found = await crud_discount.get_by_code(db_session, "OK10")
    assert found is not None and found.id == coupon_id
    assert await crud_discount.get_by_code(db_session, "PROMO") is None
    assert await crud_discount.get_by_code(db_session, "OFF") is None
    assert await crud_discount.get_by_code(db_session, "INCONNU") is None


@pytest.mark.asyncio
async def test_validate_coupon_covers_every_refusal_reason(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            _discount(code="FUTUR", start_date=_hours(+24)),
            _discount(code="PASSE", end_date=_hours(-24)),
            _discount(code="EPUISE", max_uses=3, current_uses=3),
            _discount(code="ENCORE", max_uses=3, current_uses=2),
            _discount(code="FENETRE", start_date=_hours(-1), end_date=_hours(+1)),
        ]
    )
    await db_session.flush()

    async def verdict(code: str) -> tuple[bool, str]:
        ok, message, _ = await crud_discount.validate_coupon(db_session, code)
        return ok, message

    assert await verdict("INCONNU") == (False, "Code coupon invalide")
    assert await verdict("FUTUR") == (False, "Ce coupon n'est pas encore valide")
    assert await verdict("PASSE") == (False, "Ce coupon a expiré")
    assert await verdict("EPUISE") == (
        False,
        "Ce coupon a atteint sa limite d'utilisation",
    )
    # Un usage restant, ou une fenêtre de validité en cours : valide.
    assert await verdict("ENCORE") == (True, "Coupon valide")
    ok, _, discount = await crud_discount.validate_coupon(db_session, "FENETRE")
    assert ok is True and discount is not None and discount.code == "FENETRE"


@pytest.mark.asyncio
async def test_increment_usage_counts_and_tolerates_unknown_ids(
    db_session: AsyncSession,
) -> None:
    coupon = _discount(code="UNE-FOIS", max_uses=1, current_uses=0)
    db_session.add(coupon)
    await db_session.flush()
    coupon_id = coupon.id

    updated = await crud_discount.increment_usage(db_session, coupon_id)
    assert updated.current_uses == 1
    assert updated.modify_at is not None

    # Après consommation du dernier usage, le coupon ne passe plus.
    ok, message, _ = await crud_discount.validate_coupon(db_session, "UNE-FOIS")
    assert ok is False
    assert "limite" in message

    # Id inconnu : pas d'exception, rien à renvoyer.
    assert await crud_discount.increment_usage(db_session, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_active_promotions_filter_on_dates_usage_and_target(
    db_session: AsyncSession,
) -> None:
    category = Category(name="Écrans", is_active=True)
    db_session.add(category)
    await db_session.flush()
    product = Product(name='Écran 27"', category_id=category.id)
    db_session.add(product)
    await db_session.flush()
    product_id, category_id = product.id, category.id

    def promo(**overrides: Any) -> Discount:
        return _discount(discount_type=DiscountType.PROMOTION, code=None, **overrides)

    db_session.add_all(
        [
            promo(name="Produit", target=DiscountTarget.PRODUCT, product_id=product_id),
            promo(
                name="Catégorie",
                target=DiscountTarget.CATEGORY,
                category_id=category_id,
            ),
            promo(name="Globale", target=DiscountTarget.ORDER),
            promo(name="Future", target=DiscountTarget.ORDER, start_date=_hours(+1)),
            promo(name="Finie", target=DiscountTarget.ORDER, end_date=_hours(-1)),
            promo(
                name="Épuisée", target=DiscountTarget.ORDER, max_uses=1, current_uses=1
            ),
            promo(name="Inactive", target=DiscountTarget.ORDER, is_active=False),
            # Un coupon n'est jamais une promotion automatique.
            _discount(name="Coupon", code="C1", target=DiscountTarget.ORDER),
        ]
    )
    await db_session.flush()

    names = {d.name for d in await crud_discount.get_active_promotions(db_session)}
    assert names == {"Produit", "Catégorie", "Globale"}

    by_product = await crud_discount.get_active_promotions(
        db_session, product_id=product_id
    )
    assert [d.name for d in by_product] == ["Produit"]

    by_category = await crud_discount.get_active_promotions(
        db_session, category_id=category_id
    )
    assert [d.name for d in by_category] == ["Catégorie"]

    assert (
        await crud_discount.get_active_promotions(db_session, product_id=uuid.uuid4())
        == []
    )
