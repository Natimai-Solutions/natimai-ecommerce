"""Integration test for the logistics-admin gate (RBAC allow-list)."""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_logistics_admin
from app.core.config import settings
from app.core.errors import AppError
from app.features.user.models.group import Group
from app.features.user.models.group_security import GroupSecurity
from app.features.user.models.user import User
from app.features.user.models.user_group import UserGroup

_TABLE = "shipping_route_trackings"


async def _add_user(session: AsyncSession, *, email: str, superuser: bool) -> User:
    user = User(
        email=email, is_superuser=superuser, is_active=True, hashed_password="x"
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_superuser_always_passes(db_session: AsyncSession) -> None:
    admin = await _add_user(db_session, email="su@test.local", superuser=True)
    result = await get_current_logistics_admin(current_user=admin, session=db_session)
    assert result is admin


@pytest.mark.asyncio
async def test_non_superuser_denied_when_rbac_disabled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENABLE_GROUP_PERMISSIONS", False)
    user = await _add_user(db_session, email="u@test.local", superuser=False)
    with pytest.raises(AppError) as exc:
        await get_current_logistics_admin(current_user=user, session=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ungrouped_user_denied_when_rbac_enabled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENABLE_GROUP_PERMISSIONS", True)
    user = await _add_user(db_session, email="nogroup@test.local", superuser=False)
    with pytest.raises(AppError) as exc:
        await get_current_logistics_admin(current_user=user, session=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_logistics_member_passes_when_rbac_enabled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ENABLE_GROUP_PERMISSIONS", True)
    user = await _add_user(db_session, email="log@test.local", superuser=False)
    group = Group(
        name="logistics_admin",
        group_type="security",
        priority=20,
        is_active=True,
        is_admin_active=True,
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add_all(
        [
            UserGroup(user_id=user.id, group_id=group.id),
            GroupSecurity(
                group_id=group.id,
                table_name=_TABLE,
                can_read=True,
                can_create=False,
                can_update=True,
                can_delete=False,
                is_active=True,
                is_admin_active=True,
            ),
        ]
    )
    await db_session.flush()

    result = await get_current_logistics_admin(current_user=user, session=db_session)
    assert result is user
