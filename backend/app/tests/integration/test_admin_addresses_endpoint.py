"""Integration tests: GET /admin/addresses listing (item 2).

Lists addresses across users for the validation screen, filterable by the
validation flag and enriched with the owner's email.
"""

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.address import admin_list_addresses
from app.features.user.models.address import Address
from app.features.user.models.user import User


async def _seed(session: AsyncSession) -> tuple[User, User]:
    admin = User(
        email="admin@test.local", is_active=True, is_superuser=True, hashed_password="x"
    )
    pending_user = User(
        email="pending@test.local",
        is_active=True,
        is_superuser=False,
        hashed_password="x",
    )
    validated_user = User(
        email="validated@test.local",
        is_active=True,
        is_superuser=False,
        hashed_password="x",
    )
    session.add_all([admin, pending_user, validated_user])
    await session.flush()

    session.add_all(
        [
            Address(
                user_id=pending_user.id,
                street="1 Rue A",
                city="Papeete",
                postal_code="98714",
                country="PF",
                type="shipping",
                is_validated=False,
            ),
            Address(
                user_id=validated_user.id,
                street="2 Rue B",
                city="Faaa",
                postal_code="98701",
                country="PF",
                type="shipping",
                is_validated=True,
            ),
        ]
    )
    await session.flush()
    return admin, pending_user


@pytest.mark.asyncio
async def test_admin_list_addresses_filters_pending(db_session: AsyncSession) -> None:
    admin, pending_user = await _seed(db_session)

    result = await admin_list_addresses(
        session=db_session, _current_user=admin, validated=False, skip=0, limit=100
    )

    assert result.count == 1
    assert len(result.data) == 1
    assert result.data[0].is_validated is False
    assert result.data[0].user_email == pending_user.email


@pytest.mark.asyncio
async def test_admin_list_addresses_filters_validated(
    db_session: AsyncSession,
) -> None:
    admin, _ = await _seed(db_session)

    result = await admin_list_addresses(
        session=db_session, _current_user=admin, validated=True, skip=0, limit=100
    )

    assert result.count == 1
    assert result.data[0].is_validated is True
    assert result.data[0].user_email == "validated@test.local"


@pytest.mark.asyncio
async def test_admin_list_addresses_all(db_session: AsyncSession) -> None:
    admin, _ = await _seed(db_session)

    result = await admin_list_addresses(
        session=db_session, _current_user=admin, validated=None, skip=0, limit=100
    )

    assert result.count == 2
    assert {row.user_email for row in result.data} == {
        "pending@test.local",
        "validated@test.local",
    }
