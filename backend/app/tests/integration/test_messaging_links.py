"""Integration tests (real DB): quote requests and price-group requests in the
messaging (chantier accueil et messagerie, lot MSG5)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_messaging as staff_routes
from app.api.routes import messaging as customer_routes
from app.api.routes.group_upgrade import (
    AdminReviewBody,
    approve_upgrade_request,
    submit_upgrade_request,
)
from app.features.cart.models.quote_request import QuoteRequest
from app.features.messaging import links
from app.features.messaging.models import Conversation
from app.features.product.models.price_group import PriceGroup
from app.features.user.models.group_upgrade_request import GroupUpgradeRequestCreate
from app.features.user.models.user import User

pytestmark = pytest.mark.asyncio


async def _people(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    customer = User(email=f"c+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    agent = User(
        email=f"a+{uuid.uuid4().hex[:6]}@t.local",
        hashed_password="x",
        is_superuser=True,
    )
    session.add_all([customer, agent])
    ids = (customer.id, agent.id)
    await session.commit()
    return ids


async def test_a_quote_request_opens_its_conversation_and_the_issue_answers(
    db_session: AsyncSession,
) -> None:
    customer_id, agent_id = await _people(db_session)
    customer = await db_session.get(User, customer_id)
    assert customer is not None
    quote = QuoteRequest(
        user_id=customer_id,
        email=customer.email,
        items_snapshot={
            "items": [{"product_name": "Écran"}, {"product_name": "Câble"}]
        },
    )
    db_session.add(quote)
    await db_session.flush()
    conversation = await links.open_for_quote(db_session, quote, customer=customer)
    assert conversation is not None
    conversation_id, quote_id = conversation.id, quote.id
    await db_session.commit()

    customer = await db_session.get(User, customer_id)
    assert customer is not None
    seen = await customer_routes.get_my_conversation(
        conversation_id, db_session, customer
    )
    assert seen.channel == "sales" and seen.topic == "quote"
    assert seen.context_type == "quote_request" and seen.context_id == quote_id
    assert (
        "2 article(s)" in seen.messages[0].body or "2 item(s)" in seen.messages[0].body
    )

    # The internal comment becomes a note; the issue a visible team message.
    agent = await db_session.get(User, agent_id)
    quote_row = await db_session.get(QuoteRequest, quote_id)
    assert agent is not None and quote_row is not None
    await links.quote_commented(
        db_session, quote_row, staff=agent, comment="Remise 5 %"
    )
    quote_row.quote_number = "DEV-2026-00001"
    await links.quote_issued(db_session, quote_row, staff=agent)
    await db_session.commit()

    customer = await db_session.get(User, customer_id)
    assert customer is not None
    seen = await customer_routes.get_my_conversation(
        conversation_id, db_session, customer
    )
    bodies = [m.body for m in seen.messages]
    assert any("DEV-2026-00001" in body for body in bodies)
    assert not any("Remise 5 %" in body for body in bodies)
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None
    # The quote e-mail already told the customer: no second notice.
    assert row.customer_notified_at is not None
    assert row.assigned_to_id == agent_id


async def test_a_group_request_opens_a_conversation_and_gets_the_decision(
    db_session: AsyncSession,
) -> None:
    customer_id, agent_id = await _people(db_session)
    pro = PriceGroup(
        code="PRO",
        label="Professionnels",
        requires_validation=True,
        discount_pct=Decimal("10"),
    )
    db_session.add(pro)
    pro_id = pro.id
    await db_session.commit()
    customer = await db_session.get(User, customer_id)
    assert customer is not None
    request = await submit_upgrade_request(
        session=db_session,
        current_user=customer,
        payload=GroupUpgradeRequestCreate(
            price_group_id=pro_id, business_registration_number="TAHITI-123"
        ),
    )
    conversation = await links.conversation_about(
        db_session, "group_request", request.id
    )
    assert conversation is not None
    conversation_id = conversation.id
    assert conversation.topic == "price_group"

    agent = await db_session.get(User, agent_id)
    assert agent is not None
    await approve_upgrade_request(
        request.id, db_session, agent, AdminReviewBody(comment="Bienvenue !")
    )
    customer = await db_session.get(User, customer_id)
    assert customer is not None
    seen = await customer_routes.get_my_conversation(
        conversation_id, db_session, customer
    )
    assert "TAHITI-123" in seen.messages[0].body
    assert "Professionnels" in seen.messages[-1].body
    assert "Bienvenue !" in seen.messages[-1].body
    assert (await customer_routes.my_unread_count(db_session, customer)).count == 1
    agent = await db_session.get(User, agent_id)
    assert agent is not None
    staff_view = await staff_routes.get_conversation(conversation_id, db_session, agent)
    assert staff_view.assigned_to_id == agent_id


async def test_a_quote_without_email_leaves_the_messaging_notice(
    db_session: AsyncSession,
) -> None:
    customer_id, agent_id = await _people(db_session)
    customer = await db_session.get(User, customer_id)
    assert customer is not None
    quote = QuoteRequest(
        user_id=customer_id,
        email=customer.email,
        items_snapshot={"items": [{"product_name": "Écran"}]},
    )
    db_session.add(quote)
    await db_session.flush()
    conversation = await links.open_for_quote(db_session, quote, customer=customer)
    assert conversation is not None
    conversation_id, quote_id = conversation.id, quote.id
    await db_session.commit()

    agent = await db_session.get(User, agent_id)
    quote_row = await db_session.get(QuoteRequest, quote_id)
    assert agent is not None and quote_row is not None
    quote_row.quote_number = "DEV-2026-00002"
    await links.quote_issued(db_session, quote_row, staff=agent, emailed=False)
    await db_session.commit()
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None
    # No e-mail went: the usual « a reply is waiting » notice is owed.
    assert row.customer_notified_at is None

    agent = await db_session.get(User, agent_id)
    quote_row = await db_session.get(QuoteRequest, quote_id)
    assert agent is not None and quote_row is not None
    await db_session.refresh(agent)
    await db_session.refresh(quote_row)
    await links.quote_issued(db_session, quote_row, staff=agent, emailed=True)
    await links.quote_email_not_sent(db_session, quote_row)
    await db_session.commit()
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None
    await db_session.refresh(row)
    assert row.customer_notified_at is None


async def test_nothing_is_written_while_the_module_is_off(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    customer_id, agent_id = await _people(db_session)
    customer = await db_session.get(User, customer_id)
    assert customer is not None
    quote = QuoteRequest(user_id=customer_id, email=customer.email, items_snapshot={})
    db_session.add(quote)
    await db_session.flush()
    conversation = await links.open_for_quote(db_session, quote, customer=customer)
    assert conversation is not None
    conversation_id, quote_id = conversation.id, quote.id
    await db_session.commit()

    async def off(*_args: Any) -> bool:
        return False

    monkeypatch.setattr(links, "module_enabled", off)
    agent = await db_session.get(User, agent_id)
    quote_row = await db_session.get(QuoteRequest, quote_id)
    assert agent is not None and quote_row is not None
    quote_row.quote_number = "DEV-2026-00003"
    await links.quote_issued(db_session, quote_row, staff=agent)
    await links.quote_commented(db_session, quote_row, staff=agent, comment="Note")
    await db_session.commit()
    row = await db_session.get(Conversation, conversation_id)
    assert row is not None
    await db_session.refresh(row)
    assert row.assigned_to_id is None and row.customer_notified_at is None
