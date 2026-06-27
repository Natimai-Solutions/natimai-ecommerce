"""Unit tests for the pure checkout-fulfillment helpers in cart.py."""

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.api.routes.cart import (
    FulfillmentAllocation,
    FulfillmentSegment,
    _format_fulfillment_segments_note,
    _is_polynesia_shipping_address,
    _plan_checkout_fulfillment_segments,
    _select_supplier_segment,
)
from app.core.errors import AppError
from app.features.product.models.product import Product
from app.utils.email import send_email


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        (None, True),  # no address → assume local (Polynesia)
        ("", True),
        ("BP 42, Papeete, Tahiti", True),
        ("Cours de l'Archipel, MOOREA", True),
        ("75001 Paris, France", False),
        ("10 Downing Street, London", False),
    ],
)
def test_is_polynesia_shipping_address(address: str | None, expected: bool) -> None:
    assert _is_polynesia_shipping_address(address) is expected


def test_select_supplier_segment_by_destination() -> None:
    assert _select_supplier_segment("Papeete") == FulfillmentSegment.CONSOLIDATION_PF
    assert (
        _select_supplier_segment("Paris, France") == FulfillmentSegment.SUPPLIER_DIRECT
    )


def _product() -> Product:
    return cast(Product, SimpleNamespace(id=uuid4()))


def test_plan_segments_local_covers_everything() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=3,
        local_available=Decimal("5"),
        supplier_available=Decimal("0"),
        shipping_address="Papeete",
    )
    assert segments == [
        FulfillmentAllocation(segment=FulfillmentSegment.LOCAL, quantity=Decimal("3"))
    ]


def test_plan_segments_splits_local_then_supplier_pf() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=5,
        local_available=Decimal("2"),
        supplier_available=Decimal("10"),
        shipping_address="Papeete",
    )
    assert segments == [
        FulfillmentAllocation(segment=FulfillmentSegment.LOCAL, quantity=Decimal("2")),
        FulfillmentAllocation(
            segment=FulfillmentSegment.CONSOLIDATION_PF, quantity=Decimal("3")
        ),
    ]


def test_plan_segments_supplier_direct_for_non_pf() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=4,
        local_available=Decimal("0"),
        supplier_available=Decimal("10"),
        shipping_address="Paris, France",
    )
    assert segments == [
        FulfillmentAllocation(
            segment=FulfillmentSegment.SUPPLIER_DIRECT, quantity=Decimal("4")
        )
    ]


def test_plan_segments_raises_on_insufficient_stock() -> None:
    with pytest.raises(AppError) as exc:
        _plan_checkout_fulfillment_segments(
            product=_product(),
            quantity=5,
            local_available=Decimal("1"),
            supplier_available=Decimal("1"),
            shipping_address="Papeete",
        )
    assert exc.value.status_code == 409
    assert exc.value.code == "cart.stock.insufficient"


def test_format_fulfillment_segments_note() -> None:
    assert _format_fulfillment_segments_note([]) is None
    note = _format_fulfillment_segments_note(
        [
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL, quantity=Decimal("2")
            ),
            FulfillmentAllocation(
                segment=FulfillmentSegment.CONSOLIDATION_PF, quantity=Decimal("3")
            ),
        ]
    )
    assert note == "fulfillment_segments=local:2,consolidation_pf:3"


def test_format_fulfillment_segments_note_fractional() -> None:
    note = _format_fulfillment_segments_note(
        [
            FulfillmentAllocation(
                segment=FulfillmentSegment.LOCAL, quantity=Decimal("2.5")
            )
        ]
    )
    assert note == "fulfillment_segments=local:2.5"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_send_email_stub_runs() -> None:
    # Completes without raising (the stub just logs).
    await send_email("user-1", "hello")
