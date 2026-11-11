"""Integration tests (real DB): gift cards and vouchers (R8 / confort) — the
admin issues them, the customer redeems a code into store credit, a voucher
only for its recipient, and a paid order carrying a gift-card product issues
the cards to the buyer, once, with their e-mail."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.gift_cards import (
    cancel_gift_card,
    issue_gift_cards,
    list_gift_cards,
    redeem_gift_card,
    restore_gift_card,
)
from app.core import runtime_settings
from app.core.errors import AppError
from app.features.notification.email_renderer import render_email
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.gift_card import (
    GiftCard,
    GiftCardIssue,
    GiftCardRedeem,
)
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services import gift_cards, store_credit
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User
from app.handlers import order as order_handlers
from app.handlers import payment as payment_handlers


async def _user(session: AsyncSession, *, superuser: bool = False) -> User:
    user = User(
        email=f"{'admin' if superuser else 'buyer'}+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=superuser,
        is_active=True,
        hashed_password="x",
        full_name="Tea Vahine",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _fresh(session: AsyncSession, user: User) -> User:
    await session.refresh(user)
    return user


def test_codes_are_unambiguous_and_normalized() -> None:
    code = gift_cards.generate_code()
    assert len(code) == 19 and code.count("-") == 3
    assert not set(code) & set("0O1IL-") - {"-"}
    assert gift_cards.normalize_code(" ab7k-mn3p q2rs tuvw ") == "AB7K-MN3P-Q2RS-TUVW"
    assert gift_cards.mask_code("AB7K-MN3P-Q2RS-TUVW").endswith("-TUVW")
    assert "AB7K" not in gift_cards.mask_code("AB7K-MN3P-Q2RS-TUVW")


@pytest.mark.asyncio
async def test_admin_issues_and_customer_redeems_into_store_credit(
    db_session: AsyncSession,
) -> None:
    admin = await _user(db_session, superuser=True)
    buyer = await _user(db_session)
    buyer_email = buyer.email
    cards = await issue_gift_cards(
        GiftCardIssue(amount=Decimal("5000"), count=2, note="Noël"),
        db_session,
        await _fresh(db_session, admin),
    )
    assert len(cards) == 2 and {c.state for c in cards} == {"active"}
    # Default validity: 12 months from the setting.
    assert cards[0].expires_at is not None
    assert cards[0].expires_at > datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(days=300)

    balance = await redeem_gift_card(
        GiftCardRedeem(code=cards[0].code.lower().replace("-", " ")),
        db_session,
        await _fresh(db_session, buyer),
    )
    assert balance.balance == Decimal("5000")
    assert balance.entries[0].kind == "grant"
    assert balance.entries[0].reason is not None
    assert balance.entries[0].reason.startswith("Carte cadeau ····")
    assert cards[0].code[:4] not in balance.entries[0].reason

    # Once only.
    with pytest.raises(AppError) as again:
        await redeem_gift_card(
            GiftCardRedeem(code=cards[0].code),
            db_session,
            await _fresh(db_session, buyer),
        )
    assert again.value.code == "gift_card.redeemed"
    # Unknown code: 404, nothing learnt.
    with pytest.raises(AppError) as unknown:
        await redeem_gift_card(
            GiftCardRedeem(code="ZZZZ-ZZZZ-ZZZZ-ZZZZ"),
            db_session,
            await _fresh(db_session, buyer),
        )
    assert unknown.value.status_code == 404

    # Cancelled by the admin: refused; restored: fine. A redeemed one cannot
    # be cancelled.
    cancelled = await cancel_gift_card(
        cards[1].id, db_session, await _fresh(db_session, admin)
    )
    assert cancelled.state == "cancelled"
    with pytest.raises(AppError) as off:
        await redeem_gift_card(
            GiftCardRedeem(code=cards[1].code),
            db_session,
            await _fresh(db_session, buyer),
        )
    assert off.value.code == "gift_card.cancelled"
    await restore_gift_card(cards[1].id, db_session, await _fresh(db_session, admin))
    with pytest.raises(AppError):
        await cancel_gift_card(cards[0].id, db_session, await _fresh(db_session, admin))

    listed = await list_gift_cards(
        db_session, await _fresh(db_session, admin), q="Noël", state="redeemed"
    )
    assert listed.count == 1 and listed.data[0].redeemed_by_email == buyer_email
    assert (
        await list_gift_cards(
            db_session, await _fresh(db_session, admin), q="Noël", state="active"
        )
    ).count == 1


@pytest.mark.asyncio
async def test_voucher_is_nominative_and_expiry_is_enforced(
    db_session: AsyncSession,
) -> None:
    admin = await _user(db_session, superuser=True)
    owner = await _user(db_session)
    owner_email = owner.email
    other = await _user(db_session)
    with pytest.raises(AppError) as anonymous:
        await issue_gift_cards(
            GiftCardIssue(kind="voucher", amount=Decimal("2000")),
            db_session,
            await _fresh(db_session, admin),
        )
    assert anonymous.value.code == "gift_card.recipient.required"
    (voucher,) = await issue_gift_cards(
        GiftCardIssue(
            kind="voucher",
            amount=Decimal("2000"),
            recipient_email=owner_email.upper(),
            expires_at=None,
        ),
        db_session,
        await _fresh(db_session, admin),
    )
    with pytest.raises(AppError) as not_yours:
        await redeem_gift_card(
            GiftCardRedeem(code=voucher.code),
            db_session,
            await _fresh(db_session, other),
        )
    assert not_yours.value.status_code == 404
    mine = await redeem_gift_card(
        GiftCardRedeem(code=voucher.code), db_session, await _fresh(db_session, owner)
    )
    assert mine.balance == Decimal("2000") and "Bon d'achat" in str(
        mine.entries[0].reason
    )

    (expired,) = await issue_gift_cards(
        GiftCardIssue(
            amount=Decimal("100"),
            expires_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
        ),
        db_session,
        await _fresh(db_session, admin),
    )
    assert expired.state == "expired"
    with pytest.raises(AppError) as late:
        await redeem_gift_card(
            GiftCardRedeem(code=expired.code),
            db_session,
            await _fresh(db_session, other),
        )
    assert late.value.code == "gift_card.expired"


@pytest.mark.asyncio
async def test_paid_order_issues_its_gift_cards_once_and_emails_them(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer = await _user(db_session)
    statuses = {n: OrderStatus(name=n) for n in ("Pending", "Paid")}
    pstatuses = {n: PaymentStatus(name=n) for n in ("Pending", "Completed")}
    card_product = Product(
        name="Carte cadeau 10 000",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("10000"),
        gift_card_amount=Decimal("10000"),
        supplier_name="shop",
        supplier_sku=f"gc-{uuid.uuid4().hex[:6]}",
    )
    other_product = Product(
        name="Câble",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("500"),
        supplier_name="shop",
        supplier_sku=f"cb-{uuid.uuid4().hex[:6]}",
    )
    db_session.add_all(
        [*statuses.values(), *pstatuses.values(), card_product, other_product]
    )
    await db_session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=statuses["Pending"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        total_amount=Decimal("20500"),
    )
    db_session.add(order)
    await db_session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal("20500"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=pstatuses["Completed"].id,
    )
    db_session.add_all(
        [
            OrderLine(
                order_id=order.id,
                product_id=card_product.id,
                quantity=2,
                unit_price=Decimal("10000"),
            ),
            OrderLine(
                order_id=order.id,
                product_id=other_product.id,
                quantity=1,
                unit_price=Decimal("500"),
            ),
            payment,
        ]
    )
    order_id, payment_id, buyer_id, buyer_email = (
        order.id,
        payment.id,
        buyer.id,
        buyer.email,
    )
    await db_session.commit()

    payload: dict[str, Any] = {
        "payment_id": str(payment_id),
        "order_id": str(order_id),
        "user_id": str(buyer_id),
        "provider_code": "payzen",
        "total_amount": "20500",
        "currency": "XPF",
    }
    await payment_handlers.on_payment_captured_issue_gift_cards(db_session, payload)
    cards = list(
        (
            await db_session.exec(
                select(GiftCard).where(col(GiftCard.order_id) == order_id)
            )
        ).all()
    )
    assert len(cards) == 2
    codes = [c.code for c in cards]
    card_ids = [str(c.id) for c in cards]
    assert {c.amount for c in cards} == {Decimal("10000")}
    assert all(
        c.kind == "gift_card" and c.recipient_email == buyer_email for c in cards
    )
    assert all(c.expires_at is not None for c in cards)

    # The outbox is at-least-once: a replay issues nothing more.
    await payment_handlers.on_payment_captured_issue_gift_cards(db_session, payload)
    assert (
        len(
            (
                await db_session.exec(
                    select(GiftCard).where(col(GiftCard.order_id) == order_id)
                )
            ).all()
        )
        == 2
    )

    # The e-mail carries every code, and a failed delivery is retried.
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(order_handlers, "_send_order_email", sent)
    email_payload = {
        "order_id": str(order_id),
        "user_id": str(buyer_id),
        "card_ids": card_ids,
        "currency": "XPF",
    }
    await order_handlers.on_gift_cards_issued_customer(db_session, email_payload)
    assert sent.await_args is not None
    kwargs = sent.await_args.kwargs
    assert all(code in kwargs["text"] and code in kwargs["html"] for code in codes)
    assert "cadeau" in kwargs["subject"].lower()

    monkeypatch.setattr(
        order_handlers, "_send_order_email", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(runtime_settings, "get", AsyncMock(return_value=True))
    with pytest.raises(RuntimeError):
        await order_handlers.on_gift_cards_issued_customer(db_session, email_payload)

    # The buyer gives one code away; the recipient redeems it.
    friend = await _user(db_session)
    friend_id = friend.id
    await gift_cards.redeem(db_session, code=codes[0], user=friend)
    await db_session.commit()
    assert await store_credit.balance(db_session, friend_id) == Decimal("10000")


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_gift_card_email_lists_codes(lang: str) -> None:
    email = render_email(
        "gift_card_issued",
        lang=lang,
        full_name="Tea",
        order_id=str(uuid.uuid4()),
        order_ref="CMD-1",
        cards=[
            {
                "code": "AB7K-MN3P-Q2RS-TUVW",
                "amount": "10000",
                "currency": "XPF",
                "expires_at": datetime.datetime(2027, 6, 23, tzinfo=datetime.UTC),
            }
        ],
        account_url="https://shop.test/mon-compte",
        shop_name="Natimai",
    )
    assert "AB7K-MN3P-Q2RS-TUVW" in email.text and "AB7K-MN3P-Q2RS-TUVW" in email.html
    assert "2027" in email.html
    assert "Natimai" in email.subject


async def _order_with_cards(
    session: AsyncSession, buyer: User, count: int
) -> tuple[uuid.UUID, list[str]]:
    paid = OrderStatus(name="Paid")
    session.add(paid)
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=paid.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        total_amount=Decimal(10000 * count),
    )
    session.add(order)
    await session.flush()
    order_id = order.id
    cards = await gift_cards.issue(
        session,
        kind="gift_card",
        amount=Decimal("10000"),
        count=count,
        recipient_email=buyer.email,
        order_id=order_id,
    )
    codes = [c.code for c in cards]
    await session.commit()
    return order_id, codes


@pytest.mark.asyncio
async def test_a_full_refund_takes_its_gift_cards_back(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11, S6: refunded, the order kept its cards — the buyer got
    the money back and still held 30 000 F of codes."""
    buyer = await _user(db_session)
    order_id, codes = await _order_with_cards(db_session, buyer, 3)

    # One code is still unused; one redeemed and kept; one redeemed and
    # partly spent (only 4 000 F of credit left on that account).
    keeper = await _user(db_session)
    keeper_id = keeper.id
    spender = await _user(db_session)
    spender_id = spender.id
    await gift_cards.redeem(
        db_session, code=codes[1], user=await _fresh(db_session, keeper)
    )
    await gift_cards.redeem(
        db_session, code=codes[2], user=await _fresh(db_session, spender)
    )
    await store_credit.grant(
        db_session,
        user_id=spender_id,
        amount=Decimal("-6000"),
        reason="dépensé",
        currency="XPF",
        order_id=None,
        admin=None,
    )
    await db_session.commit()

    outcome = await gift_cards.revoke_for_refund(
        db_session, order_id=order_id, fully=True
    )
    assert [c.code for c in outcome.cancelled] == [codes[0]]
    await db_session.commit()

    assert outcome.reclaimed == Decimal("14000")
    assert len(outcome.shortfalls) == 1 and "6000" in outcome.shortfalls[0]
    assert await store_credit.balance(db_session, keeper_id) == Decimal("0")
    assert await store_credit.balance(db_session, spender_id) == Decimal("0")
    message = outcome.alert("CMD-X")
    assert message is not None and "récupérer manuellement" in message

    states = {
        c.code: gift_cards.state_of(c)
        for c in (
            await db_session.exec(
                select(GiftCard).where(col(GiftCard.order_id) == order_id)
            )
        ).all()
    }
    assert states[codes[0]] == "cancelled"
    with pytest.raises(AppError):
        await gift_cards.redeem(
            db_session, code=codes[0], user=await _fresh(db_session, keeper)
        )

    # The outbox may replay the refund: nothing is taken twice.
    again = await gift_cards.revoke_for_refund(
        db_session, order_id=order_id, fully=True
    )
    assert not again.changed and again.alert("CMD-X") is None


@pytest.mark.asyncio
async def test_a_partial_refund_leaves_the_cards_to_the_admin(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer = await _user(db_session)
    order_id, codes = await _order_with_cards(db_session, buyer, 1)
    alert = AsyncMock(return_value=True)
    monkeypatch.setattr(payment_handlers, "send_alert", alert)

    await payment_handlers.on_payment_refunded(
        db_session,
        {"order_id": str(order_id), "amount": "500", "fully_refunded": False},
    )

    card = (
        await db_session.exec(
            select(GiftCard).where(col(GiftCard.order_id) == order_id)
        )
    ).one()
    assert gift_cards.state_of(card) == "active"
    assert alert.await_args is not None
    assert "remboursée en partie" in alert.await_args.args[0]
