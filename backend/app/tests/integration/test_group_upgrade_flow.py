"""Integration tests for the group-upgrade self-service flow (real Postgres)."""

import uuid

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.group_upgrade import (
    get_upgrade_group_options,
    list_my_upgrade_requests,
    submit_upgrade_request,
)
from app.core.errors import AppError
from app.features.product.models.price_group import PriceGroup
from app.features.user.models.group_upgrade_request import (
    GroupUpgradeRequestCreate,
    UpgradeRequestStatus,
)
from app.features.user.models.user import User


async def _seed(session: AsyncSession) -> tuple[User, PriceGroup, PriceGroup]:
    default_group = PriceGroup(
        code="PARTICULIER",
        label="Particulier",
        default=True,
        requires_validation=False,
        is_active=True,
    )
    pro_group = PriceGroup(
        code="PRO",
        label="Professionnel",
        default=False,
        requires_validation=True,
        is_active=True,
    )
    inactive_group = PriceGroup(
        code="OLD", label="Ancien", requires_validation=True, is_active=False
    )
    user = User(
        email=f"u+{uuid.uuid4().hex[:8]}@example.com",
        is_active=True,
        hashed_password="x",
    )
    session.add_all([default_group, pro_group, inactive_group, user])
    await session.flush()
    return user, default_group, pro_group


@pytest.mark.asyncio
async def test_options_show_default_current_and_requestable(
    db_session: AsyncSession,
) -> None:
    user, _default_group, _pro_group = await _seed(db_session)

    opts = await get_upgrade_group_options(session=db_session, current_user=user)

    # With no explicit group, the user's effective group is the default one.
    assert opts.current_group is not None
    assert opts.current_group.code == "PARTICULIER"

    codes = {g.code for g in opts.available_groups}
    assert "PRO" in codes  # requires validation → requestable
    assert "PARTICULIER" not in codes  # default group is not requestable
    assert "OLD" not in codes  # inactive group excluded

    # The internal margin rate must never be exposed to the customer.
    assert not hasattr(opts.available_groups[0], "margin_rate_pct")


@pytest.mark.asyncio
async def test_submit_then_options_excludes_assigned_group(
    db_session: AsyncSession,
) -> None:
    user, _default_group, pro_group = await _seed(db_session)
    user_id, pro_group_id = user.id, pro_group.id  # capture before commit (greenlet)

    created = await submit_upgrade_request(
        session=db_session,
        current_user=user,
        payload=GroupUpgradeRequestCreate(
            price_group_id=pro_group_id,
            business_registration_number="TAHITI-123",
        ),
    )
    assert created.status == UpgradeRequestStatus.pending

    # submit committed → re-fetch the (now expired) user instance.
    refreshed = await db_session.get(User, user_id)
    assert refreshed is not None
    user = refreshed

    # A second pending request for the same group is refused.
    with pytest.raises(AppError) as exc:
        await submit_upgrade_request(
            session=db_session,
            current_user=user,
            payload=GroupUpgradeRequestCreate(
                price_group_id=pro_group_id,
                business_registration_number="TAHITI-123",
            ),
        )
    assert exc.value.code == "user.upgrade_request.duplicate"

    listed = await list_my_upgrade_requests(session=db_session, current_user=user)
    assert listed.count == 1

    # Once on the pro group, it is no longer offered as an upgrade.
    user.price_group_id = pro_group_id
    db_session.add(user)
    await db_session.flush()
    opts = await get_upgrade_group_options(session=db_session, current_user=user)
    assert opts.current_group is not None and opts.current_group.code == "PRO"
    assert all(g.code != "PRO" for g in opts.available_groups)


@pytest.mark.asyncio
async def test_submit_for_non_validation_group_is_rejected(
    db_session: AsyncSession,
) -> None:
    user, default_group, _pro_group = await _seed(db_session)

    with pytest.raises(AppError) as exc:
        await submit_upgrade_request(
            session=db_session,
            current_user=user,
            payload=GroupUpgradeRequestCreate(
                price_group_id=default_group.id,
                business_registration_number="X",
            ),
        )
    assert exc.value.code == "user.upgrade_request.not_required"
