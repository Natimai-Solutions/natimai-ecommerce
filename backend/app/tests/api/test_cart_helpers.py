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
    _plan_checkout_fulfillment_segments,
    _supplier_segment_for_origin,
)
from app.core.errors import AppError
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.utils.email import send_email


def test_supplier_segment_is_read_from_the_supplier_place() -> None:
    dropship = cast(Place, SimpleNamespace(dropship_enabled=True))
    regular = cast(Place, SimpleNamespace(dropship_enabled=False))
    assert _supplier_segment_for_origin(dropship) == FulfillmentSegment.SUPPLIER_DIRECT
    assert (
        _supplier_segment_for_origin(regular) == FulfillmentSegment.VIA_MAIN_WAREHOUSE
    )
    # No configured origin → regroup at the main warehouse (never guess from text).
    assert _supplier_segment_for_origin(None) == FulfillmentSegment.VIA_MAIN_WAREHOUSE


def _product() -> Product:
    return cast(Product, SimpleNamespace(id=uuid4()))


def test_plan_segments_local_covers_everything() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=3,
        local_available=Decimal("5"),
        supplier_available=Decimal("0"),
    )
    assert segments == [
        FulfillmentAllocation(segment=FulfillmentSegment.LOCAL, quantity=Decimal("3"))
    ]


def test_plan_segments_splits_local_then_main_warehouse() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=5,
        local_available=Decimal("2"),
        supplier_available=Decimal("10"),
    )
    assert segments == [
        FulfillmentAllocation(segment=FulfillmentSegment.LOCAL, quantity=Decimal("2")),
        FulfillmentAllocation(
            segment=FulfillmentSegment.VIA_MAIN_WAREHOUSE, quantity=Decimal("3")
        ),
    ]


def test_plan_segments_supplier_direct_when_dropship() -> None:
    segments = _plan_checkout_fulfillment_segments(
        product=_product(),
        quantity=4,
        local_available=Decimal("0"),
        supplier_available=Decimal("10"),
        supplier_segment=FulfillmentSegment.SUPPLIER_DIRECT,
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
                segment=FulfillmentSegment.VIA_MAIN_WAREHOUSE, quantity=Decimal("3")
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
