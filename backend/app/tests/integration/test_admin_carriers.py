"""Integration tests: admin carrier management and carrier data on the journey."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_shipping import (
    CarrierPatchRequest,
    CarrierWriteRequest,
    ShipRequest,
    create_carrier,
    list_carriers,
    order_journey,
    retire_carrier,
    ship_tracking,
    update_carrier,
)
from app.core.errors import AppError
from app.features.shipping.services.tracking_url import validate_tracking_url_template
from app.features.user.models.user import User
from app.tests.integration.factories import seed_shipping_scenario


def _detached_admin(seed: SimpleNamespace) -> User:
    """Endpoints commit; a plain id-holder avoids touching an expired ORM row."""
    return cast(User, SimpleNamespace(id=seed.admin.id))


_DHL = "https://www.dhl.com/track?id={ref}"


@pytest.mark.asyncio
async def test_carrier_lifecycle(db_session: AsyncSession) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=1)
    admin = _detached_admin(seed)

    created = await create_carrier(
        body=CarrierWriteRequest(
            name=" DHL ", code="DHL Express", tracking_url_template=_DHL
        ),
        session=db_session,
        admin=admin,
    )
    assert created.name == "DHL"
    assert created.code == "dhl_express"  # normalized slug
    assert created.tracking_url_template == _DHL

    # Duplicate code is refused whatever the case / spacing.
    with pytest.raises(AppError) as dup:
        await create_carrier(
            body=CarrierWriteRequest(name="Dup", code="dhl-express"),
            session=db_session,
            admin=admin,
        )
    assert dup.value.code == "carrier.code.duplicate"

    updated = await update_carrier(
        carrier_id=created.id,
        body=CarrierPatchRequest(name="DHL Express", tracking_url_template=""),
        session=db_session,
        _admin=admin,
    )
    assert updated.name == "DHL Express"
    assert updated.tracking_url_template is None  # blank → no public tracking page

    await retire_carrier(carrier_id=created.id, session=db_session, _admin=admin)
    active = await list_carriers(
        session=db_session, _admin=admin, include_inactive=False
    )
    everyone = await list_carriers(
        session=db_session, _admin=admin, include_inactive=True
    )
    assert all(c.id != created.id for c in active)
    assert any(c.id == created.id and c.is_active is False for c in everyone)

    restored = await update_carrier(
        carrier_id=created.id,
        body=CarrierPatchRequest(is_active=True),
        session=db_session,
        _admin=admin,
    )
    assert restored.is_active is True


@pytest.mark.asyncio
async def test_carrier_template_must_be_https_with_placeholder(
    db_session: AsyncSession,
) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=1)
    admin = _detached_admin(seed)
    for bad in (
        "http://insecure/{ref}",
        "https://no-placeholder.example",
        "javascript:x",
    ):
        with pytest.raises(AppError) as exc:
            await create_carrier(
                body=CarrierWriteRequest(
                    name="X", code=f"x{uuid.uuid4().hex[:6]}", tracking_url_template=bad
                ),
                session=db_session,
                admin=admin,
            )
        assert exc.value.code == "carrier.tracking_url_template.invalid"

    with pytest.raises(AppError) as missing:
        await update_carrier(
            carrier_id=uuid.uuid4(),
            body=CarrierPatchRequest(name="ghost"),
            session=db_session,
            _admin=admin,
        )
    assert missing.value.code == "carrier.not_found"


def test_validate_tracking_url_template_unit() -> None:
    assert validate_tracking_url_template(None) is None
    assert validate_tracking_url_template("   ") is None
    assert validate_tracking_url_template(f" {_DHL} ") == _DHL
    with pytest.raises(ValueError):
        validate_tracking_url_template("https://x.example/no-ref")


@pytest.mark.asyncio
async def test_journey_exposes_carrier_and_tracking_link(
    db_session: AsyncSession,
) -> None:
    seed = await seed_shipping_scenario(db_session, n_trackings=2)
    admin = _detached_admin(seed)
    carrier = await create_carrier(
        body=CarrierWriteRequest(name="DHL", code="dhl", tracking_url_template=_DHL),
        session=db_session,
        admin=admin,
    )

    first_tracking_id = seed.tracking_ids[0]
    await ship_tracking(
        tracking_id=first_tracking_id,
        body=ShipRequest(tracking_ref="A B", carrier_id=carrier.id),
        session=db_session,
        admin=admin,
    )

    legs = await order_journey(order_id=seed.order_id, session=db_session, _admin=admin)
    assert legs[0].carrier_id == carrier.id
    assert legs[0].carrier_name == "DHL"
    assert legs[0].tracking_url == "https://www.dhl.com/track?id=A%20B"
    assert legs[0].is_final_leg is False
    assert legs[0].is_terminal is False  # shipped is not terminal
    assert legs[1].carrier_id is None
    assert legs[1].tracking_url is None
    assert legs[1].is_final_leg is True  # highest sequence of the journey
