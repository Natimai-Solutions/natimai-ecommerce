"""Integration tests (real DB): the team's tools (chantier accueil et
messagerie, lot MSG4) — prepared answers, priority groups first in the queue,
the morning digest."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_messaging as staff_routes
from app.api.routes import messaging as customer_routes
from app.features.messaging import notify
from app.features.product.models.price_group import PriceGroup
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
        hashed_password="x",
        is_active=True,
        is_verified=True,
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


async def test_prepared_answers_by_channel(db_session: AsyncSession) -> None:
    admin = await _user(db_session, "admin", is_superuser=True)
    seller = await _user(db_session, "seller", staff_role="sales")
    for channel, title in (
        (None, "Bonjour"),
        ("sales", "Devis"),
        ("technical", "Panne"),
    ):
        await staff_routes.create_canned_reply(
            staff_routes.CannedReplyWrite(
                channel=channel,
                title=title,
                body=f"{title}, {{prenom}} !",
                translations={"en": {"title": f"{title} EN", "body": "Hello {prenom}"}},
            ),
            db_session,
            await _get(db_session, admin),
        )
    seen = await staff_routes.list_canned_replies(
        db_session, await _get(db_session, seller)
    )
    assert [r.title for r in seen] == ["Bonjour", "Devis"]
    assert seen[0].translations["en"]["body"] == "Hello {prenom}"


async def test_priority_groups_come_first_and_the_digest(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    pro = PriceGroup(code="pro", label="Pro", messaging_priority=True)
    db_session.add_all(
        [PriceGroup(code="particulier", label="Particulier", default=True), pro]
    )
    pro_id = pro.id
    await db_session.commit()
    agent = await _user(db_session, "agent", is_superuser=True)
    first = await _user(db_session, "first")
    vip = await _user(db_session, "vip", price_group_id=pro_id)
    ids = []
    for customer in (first, vip):
        created = await customer_routes.open_my_conversation(
            customer_routes.ConversationCreate(topic="delivery", body="Bonjour"),
            db_session,
            await _get(db_session, customer),
        )
        ids.append(created.id)

    page = await staff_routes.list_conversations(
        db_session, await _get(db_session, agent), tab="todo"
    )
    # The pro customer wrote second but comes first, marked.
    assert [c.id for c in page.data] == [ids[1], ids[0]]
    assert [c.priority for c in page.data] == [True, False]

    sent: list[dict[str, Any]] = []

    async def queue_email(_session: Any, **kwargs: Any) -> uuid.UUID:
        sent.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(notify, "queue_email", queue_email)
    assert await notify.staff_digest(db_session) == 1
    assert "2" in sent[0]["subject"] and "Bonjour" not in sent[0]["text"]
