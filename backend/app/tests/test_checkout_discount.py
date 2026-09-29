"""Unit: promo codes at checkout — eligibility, amount, split, refusals.

The database is simulated: the rules are what is tested, not the SQL.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.discount.models import DiscountTarget, DiscountType
from app.features.discount.services import checkout_discount as svc


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _discount(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "Rentrée -10 %",
        "code": "RENTREE10",
        "discount_type": DiscountType.COUPON,
        "is_active": True,
        "is_admin_active": True,
        "percentage": Decimal("10"),
        "amount": None,
        "min_order_amount": None,
        "max_uses": None,
        "max_uses_per_customer": None,
        "current_uses": 0,
        "start_date": None,
        "end_date": None,
        "target": DiscountTarget.ORDER,
        "product_id": None,
        "category_id": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _item(product_id: uuid.UUID, price: str, qty: int) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(), product_id=product_id, unit_price=Decimal(price), quantity=qty
    )


def _session(discount: Any | None, *, customer_uses: int = 0) -> Any:
    """First exec serves the coupon lookup, the second the per-customer count."""
    lookup = MagicMock()
    lookup.first.return_value = discount
    count = MagicMock()
    count.one.return_value = customer_uses
    session = MagicMock()
    session.exec = AsyncMock(side_effect=[lookup, count])
    return session


def test_split_amount_sums_exactly_with_xpf_rounding() -> None:
    keys = [uuid.uuid4() for _ in range(3)]
    weights = [
        (keys[0], Decimal("1000")),
        (keys[1], Decimal("1000")),
        (keys[2], Decimal("1000")),
    ]
    shares = svc.split_amount(Decimal("100"), weights, "XPF")
    assert sum(shares.values()) == Decimal("100")
    assert sorted(shares.values()) == [Decimal("33"), Decimal("33"), Decimal("34")]


def test_split_amount_uses_cents_for_a_subunit_currency() -> None:
    keys = [uuid.uuid4(), uuid.uuid4()]
    shares = svc.split_amount(
        Decimal("10.00"), [(keys[0], Decimal("2")), (keys[1], Decimal("1"))], "EUR"
    )
    assert shares[keys[0]] == Decimal("6.67")
    assert shares[keys[1]] == Decimal("3.33")


@pytest.mark.anyio
async def test_percentage_on_the_whole_order() -> None:
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    items = [_item(p1, "1000", 2), _item(p2, "500", 1)]
    products = {
        p1: SimpleNamespace(id=p1, category_id=None),
        p2: SimpleNamespace(id=p2, category_id=None),
    }
    applied = await svc.resolve_coupon(
        _session(_discount()),
        code=" rentree10 ",
        user_id=uuid.uuid4(),
        items=items,
        products_by_id=products,
        currency="XPF",
    )
    assert applied.code == "RENTREE10"
    assert applied.amount == Decimal("250")
    assert applied.line_amounts[items[0].id] == Decimal("200")
    assert applied.line_amounts[items[1].id] == Decimal("50")


@pytest.mark.anyio
async def test_fixed_amount_is_capped_to_the_eligible_lines() -> None:
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    items = [_item(p1, "300", 1), _item(p2, "5000", 1)]
    products = {
        p1: SimpleNamespace(id=p1, category_id=None),
        p2: SimpleNamespace(id=p2, category_id=None),
    }
    discount = _discount(
        percentage=None,
        amount=Decimal("1000"),
        target=DiscountTarget.PRODUCT,
        product_id=p1,
    )
    applied = await svc.resolve_coupon(
        _session(discount),
        code="RENTREE10",
        user_id=uuid.uuid4(),
        items=items,
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("300")  # never more than the line itself
    assert applied.line_amounts == {items[0].id: Decimal("300")}


@pytest.mark.anyio
async def test_category_target_only_touches_its_lines() -> None:
    cat = uuid.uuid4()
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    items = [_item(p1, "1000", 1), _item(p2, "1000", 1)]
    products = {
        p1: SimpleNamespace(id=p1, category_id=cat),
        p2: SimpleNamespace(id=p2, category_id=None),
    }
    discount = _discount(target=DiscountTarget.CATEGORY, category_id=cat)
    applied = await svc.resolve_coupon(
        _session(discount),
        code="RENTREE10",
        user_id=uuid.uuid4(),
        items=items,
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("100")
    assert applied.line_amounts == {items[0].id: Decimal("100")}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("discount", "customer_uses", "reason"),
    [
        (None, 0, "unknown"),
        (_discount(is_active=False), 0, "unknown"),
        (
            _discount(start_date=datetime.datetime.now() + datetime.timedelta(days=1)),
            0,
            "not_started",
        ),
        (
            _discount(end_date=datetime.datetime.now() - datetime.timedelta(days=1)),
            0,
            "expired",
        ),
        (_discount(max_uses=5, current_uses=5), 0, "exhausted"),
        (_discount(max_uses_per_customer=1), 1, "customer_limit"),
        (_discount(min_order_amount=Decimal("5000")), 0, "below_minimum"),
        (
            _discount(target=DiscountTarget.PRODUCT, product_id=uuid.uuid4()),
            0,
            "not_applicable",
        ),
        (_discount(percentage=None, amount=None), 0, "misconfigured"),
    ],
)
async def test_refusals_name_their_reason(
    discount: Any, customer_uses: int, reason: str
) -> None:
    p1 = uuid.uuid4()
    with pytest.raises(svc.DiscountRefused) as raised:
        await svc.resolve_coupon(
            _session(discount, customer_uses=customer_uses),
            code="RENTREE10",
            user_id=uuid.uuid4(),
            items=[_item(p1, "1000", 1)],
            products_by_id={p1: SimpleNamespace(id=p1, category_id=None)},
            currency="XPF",
        )
    assert raised.value.reason == reason
    assert raised.value.message
