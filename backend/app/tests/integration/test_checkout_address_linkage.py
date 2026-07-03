"""Integration tests: checkout links the tracking to the customer's saved
address by id instead of re-matching free text.

Regression guard for the address-duplication bug: passing ``shipping_address_id``
must reuse the existing Address (no duplicate), even when the free-text snapshot
would not match the stored ``street, city, country``.
"""

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import _resolve_tracking_address_for_checkout
from app.features.user.models.address import Address
from app.features.user.models.user import User


async def _seed_user_with_address(session: AsyncSession) -> tuple[User, Address]:
    user = User(
        email="buyer@test.local",
        is_active=True,
        is_superuser=False,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    address = Address(
        user_id=user.id,
        street="123 Rue des Îles",
        city="Papeete",
        postal_code="98714",
        country="PF",
        type="shipping",
    )
    session.add(address)
    await session.flush()
    return user, address


async def _count_addresses(session: AsyncSession, user_id: object) -> int:
    result = await session.exec(select(Address).where(Address.user_id == user_id))
    return len(result.all())


@pytest.mark.asyncio
async def test_resolve_reuses_saved_address_by_id(db_session: AsyncSession) -> None:
    user, address = await _seed_user_with_address(db_session)
    address_id = address.id

    # The free-text snapshot deliberately differs from the stored fields (this is
    # exactly what used to trigger a duplicate). The id must win.
    resolved = await _resolve_tracking_address_for_checkout(
        db_session,
        current_user=user,
        shipping_address="123 Rue des Îles, 98714 Papeete, Tahiti, PF",
        shipping_address_id=address_id,
    )

    assert resolved.id == address_id
    assert await _count_addresses(db_session, user.id) == 1  # no duplicate created


@pytest.mark.asyncio
async def test_resolve_reuses_by_exact_text_when_no_id(
    db_session: AsyncSession,
) -> None:
    user, address = await _seed_user_with_address(db_session)
    address_id = address.id

    # No id, but the text matches "street, city, country" exactly → reuse, no dup.
    resolved = await _resolve_tracking_address_for_checkout(
        db_session,
        current_user=user,
        shipping_address="123 Rue des Îles, Papeete, PF",
        shipping_address_id=None,
    )

    assert resolved.id == address_id
    assert await _count_addresses(db_session, user.id) == 1


@pytest.mark.asyncio
async def test_resolve_creates_snapshot_when_unmatched(
    db_session: AsyncSession,
) -> None:
    user, address = await _seed_user_with_address(db_session)

    # No id and non-matching text → a snapshot address is created (guest/manual).
    resolved = await _resolve_tracking_address_for_checkout(
        db_session,
        current_user=user,
        shipping_address="99 Autre Rue, 98701 Faaa, PF",
        shipping_address_id=None,
    )

    assert resolved.id != address.id
    assert await _count_addresses(db_session, user.id) == 2
