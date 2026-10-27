"""The signed tracking link of an order: valid for its order only, and only
for TRACKING_LINK_DAYS after the order."""

import uuid
from datetime import UTC, datetime, timedelta

from app.features.order.services.tracking_link import (
    TRACKING_LINK_DAYS,
    order_tracking_token,
    tracking_link_still_valid,
    verify_order_tracking_token,
)


def test_the_token_opens_its_order_only() -> None:
    order_id, other = uuid.uuid4(), uuid.uuid4()
    token = order_tracking_token(order_id)
    assert verify_order_tracking_token(order_id, token)
    assert not verify_order_tracking_token(other, token)
    assert not verify_order_tracking_token(order_id, None)


def test_the_link_expires_after_the_retention() -> None:
    now = datetime(2026, 10, 25, tzinfo=UTC)
    recent = now - timedelta(days=TRACKING_LINK_DAYS - 1)
    old = now - timedelta(days=TRACKING_LINK_DAYS + 1)
    assert tracking_link_still_valid(recent, now=now)
    assert not tracking_link_still_valid(old, now=now)
    # Naive timestamps are UTC wall-clock.
    assert not tracking_link_still_valid(old.replace(tzinfo=None), now=now)
