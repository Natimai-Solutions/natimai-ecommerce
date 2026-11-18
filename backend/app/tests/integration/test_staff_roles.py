"""Integration tests (real DB): the back-office team roles (chantier accueil et
messagerie, lot ROLE) — each role reaches its channels and screens only, by
allow-list, and signs in like an administrator."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api import deps
from app.api.routes import admin_messaging as staff_routes
from app.api.routes import admin_users
from app.api.routes import messaging as customer_routes
from app.core.config import settings
from app.core.errors import AppError
from app.features.user.models.user import User

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def never(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(customer_routes, "hit_rate_limit", never)


async def _user(session: AsyncSession, key: str, **fields: Any) -> uuid.UUID:
    user = User(
        email=f"{key}+{uuid.uuid4().hex[:6]}@t.local",
        full_name=key.capitalize(),
        hashed_password="x",
        is_active=True,
        is_verified=True,
        totp_enabled=True,
        **fields,
    )
    session.add(user)
    user_id = user.id
    await session.commit()
    return user_id


async def _get(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    await session.refresh(user)
    return user


async def _open(session: AsyncSession, customer_id: uuid.UUID, topic: str) -> uuid.UUID:
    body = customer_routes.ConversationCreate(topic=topic, body="Bonjour")
    created = await customer_routes.open_my_conversation(
        body, session, await _get(session, customer_id)
    )
    return created.id


async def test_each_role_works_on_its_channels_only(db_session: AsyncSession) -> None:
    customer = await _user(db_session, "client")
    support = await _user(db_session, "support", staff_role="customer_service")
    seller = await _user(db_session, "seller", staff_role="sales")
    delivery = await _open(db_session, customer, "delivery")
    fault = await _open(db_session, customer, "fault")
    quote = await _open(db_session, customer, "quote")

    async def queue(user_id: uuid.UUID) -> set[uuid.UUID]:
        page = await staff_routes.list_conversations(
            db_session, await _get(db_session, user_id), tab="all"
        )
        return {c.id for c in page.data}

    assert await queue(support) == {delivery, fault}
    assert await queue(seller) == {quote}
    summary = await staff_routes.conversations_summary(
        db_session, await _get(db_session, seller)
    )
    assert summary.todo == 1

    # Another channel's conversation reads as missing.
    with pytest.raises(AppError) as hidden:
        await staff_routes.get_conversation(
            quote, db_session, await _get(db_session, support)
        )
    assert hidden.value.status_code == 404

    # A transfer goes to someone whose role covers the channel.
    with pytest.raises(AppError) as refused:
        await staff_routes.transfer_conversation(
            delivery,
            staff_routes.TransferBody(user_id=seller),
            db_session,
            await _get(db_session, support),
        )
    assert refused.value.code == "messaging.invalid_assignee"
    team = await staff_routes.conversation_team(
        db_session, await _get(db_session, support), channel="sales"
    )
    assert [m.id for m in team] == [seller]


async def test_allow_lists_and_second_factor(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = [
        await _user(db_session, "support", staff_role="customer_service"),
        await _user(db_session, "seller", staff_role="sales"),
        await _user(db_session, "client"),
    ]
    support, seller, customer = [await _get(db_session, i) for i in ids]

    assert await deps.get_current_quote_staff(seller) is seller
    for outsider in (support, customer):
        with pytest.raises(AppError) as refused:
            await deps.get_current_quote_staff(outsider)
        assert refused.value.status_code == 403
    assert await deps.get_current_order_reader(support) is support
    with pytest.raises(AppError):
        await deps.get_current_order_reader(customer)
    with pytest.raises(AppError):
        await deps.get_current_active_superuser(seller)

    # A team member signs in like an administrator: 2FA required.
    monkeypatch.setattr(settings, "ADMIN_2FA_REQUIRED", True)
    support.totp_enabled = False
    assert deps.must_enrol_second_factor(support)
    assert not deps.must_enrol_second_factor(customer)


async def test_a_superuser_gives_and_takes_a_role(db_session: AsyncSession) -> None:
    admin_id = await _user(db_session, "admin", is_superuser=True)
    member_id = await _user(db_session, "member")
    member = await _get(db_session, member_id)
    stamp = member.security_stamp

    updated = await admin_users.update_user(
        member_id,
        admin_users.AdminUserUpdate(staff_role="sales"),
        db_session,
        await _get(db_session, admin_id),
    )
    assert updated.staff_role == "sales"
    # Rights changed: the open sessions end.
    assert (await _get(db_session, member_id)).security_stamp != stamp

    for role, target in (("boss", member_id), ("sales", admin_id)):
        with pytest.raises(AppError) as refused:
            await admin_users.update_user(
                target,
                admin_users.AdminUserUpdate(staff_role=role),
                db_session,
                await _get(db_session, admin_id),
            )
        assert refused.value.status_code == 400
