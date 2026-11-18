"""Integration tests (real DB): the public contact (chantier accueil et
messagerie, lot MSG2) — the same answer whatever the address, nothing sent to
the address typed, the team's reply by e-mail with a link, and the link that
attaches the visitor's conversations to an account."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import Response
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.api.routes import admin_messaging as staff_routes
from app.api.routes import contact as routes
from app.api.routes import messaging as customer_routes
from app.core.errors import AppError
from app.features.messaging import guests
from app.features.messaging.models import Conversation
from app.features.user.models.user import User

pytestmark = pytest.mark.asyncio


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("203.0.113.9", 1234),
            "path": "/contact",
            "headers": [],
            "query_string": b"",
        }
    )


@pytest.fixture(autouse=True)
def _no_limits(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    async def never(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(routes, "hit_rate_limit", never)
    return []


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    outbox: list[dict[str, Any]] = []

    async def queue_email(_session: Any, **kwargs: Any) -> uuid.UUID:
        outbox.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(guests, "queue_email", queue_email)
    return outbox


def _form(**fields: Any) -> routes.ContactRequest:
    return routes.ContactRequest.model_validate(
        {
            "topic": "pre_sale",
            "name": "Teva",
            "email": "teva@example.com",
            "body": "Ce portable tient-il une journée ?",
            **fields,
        }
    )


async def _conversations(session: AsyncSession) -> list[Conversation]:
    session.expire_all()
    return list((await session.exec(select(Conversation))).all())


async def test_same_answer_and_nothing_sent_to_the_address(
    db_session: AsyncSession, sent: list[dict[str, Any]]
) -> None:
    db_session.add(
        User(
            email="client@example.com",
            hashed_password="x",
            is_active=True,
            is_verified=True,
        )
    )
    await db_session.commit()

    unknown = await routes.contact(_form(), _request(), db_session)
    known = await routes.contact(
        _form(email="client@example.com"), _request(), db_session
    )
    robot = await routes.contact(
        _form(email="robot@example.com", website="http://spam"), _request(), db_session
    )
    assert unknown == known == robot
    assert sent == []  # no acknowledgement to an unproven address

    rows = await _conversations(db_session)
    assert sorted(c.guest_email or "" for c in rows) == [
        "client@example.com",
        "teva@example.com",
    ]
    # A visitor's request never lands in an account by its e-mail alone.
    assert all(c.customer_id is None for c in rows)

    # Writing again on the same address joins the open conversation.
    await routes.contact(_form(body="Et la garantie ?"), _request(), db_session)
    assert len(await _conversations(db_session)) == 2


async def test_reply_by_email_then_signup_through_the_link(
    db_session: AsyncSession, sent: list[dict[str, Any]]
) -> None:
    agent = User(
        email=f"agent+{uuid.uuid4().hex[:6]}@t.local",
        hashed_password="x",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(agent)
    await db_session.commit()
    await routes.contact(_form(), _request(), db_session)
    conversation = (await _conversations(db_session))[0]
    conversation_id = conversation.id

    await db_session.refresh(agent)
    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Oui, 10 heures <b>environ</b>."),
        db_session,
        agent,
    )
    assert len(sent) == 1
    email = sent[0]
    assert email["recipient"] == "teva@example.com"
    assert email["resendable"] is False  # the link is a secret
    assert "10 heures" in email["text"]
    assert "&lt;b&gt;environ" in email["html"]  # escaped in the HTML part
    token = email["text"].split("/contact/suite/")[1].split()[0]

    info = await routes.continue_info(token, db_session)
    assert info.email == "teva@example.com" and info.account == "none"

    tokens = await routes.continue_with_signup(
        token,
        routes.ContinueSignup(password="motdepasse-solide"),
        db_session,
        Response(),
    )
    assert tokens.access_token
    user = (
        await db_session.exec(select(User).where(col(User.email) == "teva@example.com"))
    ).one()
    assert user.is_verified and not user.is_guest
    user_id = user.id
    attached = await db_session.get(Conversation, conversation_id)
    assert attached is not None and attached.customer_id == user_id

    # Used once: the link no longer opens anything.
    with pytest.raises(AppError) as used:
        await routes.continue_info(token, db_session)
    assert used.value.code == "messaging.link_invalid"
    seen = await customer_routes.list_my_conversations(db_session, user)
    assert [c.id for c in seen] == [conversation_id]


async def test_an_existing_account_signs_in_and_only_its_own_address_attaches(
    db_session: AsyncSession, sent: list[dict[str, Any]]
) -> None:
    owner = User(
        email="teva@example.com", hashed_password="x", is_active=True, is_verified=True
    )
    other = User(
        email="autre@example.com", hashed_password="x", is_active=True, is_verified=True
    )
    agent = User(
        email="agent@t.local", hashed_password="x", is_active=True, is_superuser=True
    )
    db_session.add_all([owner, other, agent])
    await db_session.commit()
    await routes.contact(_form(), _request(), db_session)
    conversation_id = (await _conversations(db_session))[0].id
    await db_session.refresh(agent)
    await staff_routes.post_staff_message(
        conversation_id,
        staff_routes.StaffMessageCreate(body="Réponse"),
        db_session,
        agent,
    )
    token = sent[0]["text"].split("/contact/suite/")[1].split()[0]

    assert (await routes.continue_info(token, db_session)).account == "account"
    with pytest.raises(AppError) as exists:
        await routes.continue_with_signup(
            token,
            routes.ContinueSignup(password="motdepasse-solide"),
            db_session,
            Response(),
        )
    assert exists.value.code == "messaging.link_account_exists"

    await db_session.refresh(other)
    with pytest.raises(AppError) as foreign:
        await routes.continue_signed_in(token, db_session, other)
    assert foreign.value.code == "messaging.link_invalid"

    await db_session.refresh(owner)
    owner_id = owner.id
    attached = await routes.continue_signed_in(token, db_session, owner)
    assert attached.conversation_id == conversation_id
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None and row.customer_id == owner_id
