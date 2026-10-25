"""Integration tests (real DB): a quote request becomes an issued quote
(DEV number, frozen snapshot, PDF, e-mail with the PDF attached), the
customer sees it, loads it into the cart at the quoted prices, and the
guards that keep an expired or converted quote from being ordered."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.api.routes.admin_quote_requests import (
    download_quote_pdf,
    get_quote_request,
    issue_quote_request,
)
from app.core.errors import AppError
from app.features.cart.models.quote_request import QuoteRequest, QuoteRequestStatus
from app.features.cart.services import quote as quote_service
from app.features.cart.services.quote import QuoteIssueBody, QuoteLine, quoted_prices
from app.features.invoice.services.pdf import PdfRenderingUnavailableError
from app.features.notification import mailer
from app.features.notification.providers import NotificationResult
from app.features.product.models.product import Product
from app.features.user.models.user import User


async def _seed(session: AsyncSession) -> SimpleNamespace:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Alice Tama",
        is_active=True,
        hashed_password="x",
    )
    laptop = Product(
        name="Station de travail",
        vendor_part_number="WS-1",
        base_price=Decimal("150000"),
    )
    screen = Product(name='Écran 27"', base_price=Decimal("45000"))
    session.add_all([admin, buyer, laptop, screen])
    await session.flush()
    request = QuoteRequest(
        user_id=buyer.id,
        email=buyer.email,
        full_name="Alice Tama",
        shipping_address="BP 42, Papeete",
        items_snapshot={
            "currency": "XPF",
            "subtotal_amount": "240000.00",
            "items": [
                {
                    "product_id": str(laptop.id),
                    "product_name": laptop.name,
                    "quantity": "1",
                    "unit_price": "150000.00",
                },
                {
                    "product_id": str(screen.id),
                    "product_name": screen.name,
                    "quantity": "2",
                    "unit_price": "45000.00",
                },
            ],
        },
    )
    session.add(request)
    await session.flush()
    seed = SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        buyer=cast(User, SimpleNamespace(id=buyer.id, email=buyer.email)),
        stranger=cast(User, SimpleNamespace(id=admin.id, email="other@test.local")),
        quote_id=request.id,
        laptop_id=laptop.id,
        screen_id=screen.id,
    )
    await session.commit()
    return seed


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Capture the customer e-mails (provider mocked)."""
    messages: list[Any] = []

    class _Provider:
        async def send(self, message: Any) -> NotificationResult:
            messages.append(message)
            return NotificationResult(provider_code="fake", delivered=True)

    monkeypatch.setattr(mailer, "get_notification_provider", lambda _code: _Provider())
    return messages


@pytest.mark.asyncio
async def test_issuing_freezes_the_quote_numbers_it_and_mails_the_pdf(
    db_session: AsyncSession, sent: list[Any]
) -> None:
    seed = await _seed(db_session)

    # The admin starts from the request's cart, grants a price and a delivery fee.
    detail = await get_quote_request(seed.quote_id, db_session, seed.admin)
    assert [ln.unit_price for ln in detail.proposed_lines] == [
        Decimal("150000"),
        Decimal("45000"),
    ]
    assert detail.quote_number is None

    body = QuoteIssueBody(
        lines=[
            QuoteLine(
                product_id=seed.laptop_id,
                product_name="Station de travail",
                quantity=1,
                unit_price=Decimal("140000"),
            ),
            QuoteLine(
                product_id=seed.screen_id,
                product_name='Écran 27"',
                quantity=2,
                unit_price=Decimal("42000"),
            ),
        ],
        shipping_fee_amount=Decimal("5000"),
        customer_message="Prix valables pour une commande groupée d'octobre.",
    )
    issued = await issue_quote_request(seed.quote_id, body, db_session, seed.admin)
    assert issued.quote_number == "DEV-2026-00001"
    assert issued.status == QuoteRequestStatus.QUOTED.value
    assert issued.valid_until == date.today() + timedelta(days=30)
    snapshot = issued.quote_snapshot or {}
    assert (
        snapshot["subtotal_amount"] == "224000" and snapshot["total_amount"] == "229000"
    )
    assert snapshot["lines"][0]["reference"] == "WS-1"
    assert snapshot["buyer"]["name"] == "Alice Tama"
    assert issued.email_sent
    message = sent[-1]
    assert "DEV-2026-00001" in message.subject and "229000" in message.subject
    assert message.recipient == seed.buyer.email
    assert message.attachments and message.attachments[0][0] == "DEV-2026-00001.pdf"
    assert message.attachments[0][1][:4] == b"%PDF"

    # Re-issuing corrects the quote and keeps its number.
    body.lines[1].unit_price = Decimal("40000")
    body.send_email = False
    again = await issue_quote_request(seed.quote_id, body, db_session, seed.admin)
    assert again.quote_number == "DEV-2026-00001" and not again.email_sent
    assert (again.quote_snapshot or {})["total_amount"] == "225000"

    # The PDF is served to the admin and to the customer, not to a stranger.
    response = await download_quote_pdf(seed.quote_id, db_session, seed.admin)
    assert (
        response.media_type == "application/pdf" and bytes(response.body)[:4] == b"%PDF"
    )
    mine = await cart_routes.download_my_quote_pdf(
        seed.quote_id, db_session, seed.buyer
    )
    assert 'filename="DEV-2026-00001.pdf"' in mine.headers["content-disposition"]
    with pytest.raises(AppError) as denied:
        await cart_routes.download_my_quote_pdf(
            seed.quote_id, db_session, seed.stranger
        )
    assert denied.value.code == "quote.not_found"


@pytest.mark.asyncio
@pytest.mark.usefixtures("sent")
async def test_the_customer_orders_the_quote_at_the_quoted_prices(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)

    async def plain_product(session: Any, *, product_id: uuid.UUID) -> Product:
        product = await session.get(Product, product_id)
        assert isinstance(product, Product)
        return product

    monkeypatch.setattr(cart_routes, "_get_active_product_or_404", plain_product)

    # Not issued yet: listed, not orderable.
    mine = await cart_routes.list_my_quotes(db_session, seed.buyer)
    assert len(mine) == 1 and not mine[0].can_order
    with pytest.raises(AppError) as not_issued:
        await cart_routes.accept_my_quote(seed.quote_id, db_session, seed.buyer)
    assert not_issued.value.code == "quote.not_issued"

    await issue_quote_request(
        seed.quote_id,
        QuoteIssueBody(
            lines=[
                QuoteLine(
                    product_id=seed.laptop_id,
                    product_name="Station",
                    quantity=1,
                    unit_price=Decimal("140000"),
                ),
                QuoteLine(
                    product_id=seed.screen_id,
                    product_name="Écran",
                    quantity=2,
                    unit_price=Decimal("42000"),
                ),
            ],
            shipping_fee_amount=Decimal("5000"),
            send_email=False,
        ),
        db_session,
        seed.admin,
    )
    mine = await cart_routes.list_my_quotes(db_session, seed.buyer)
    assert mine[0].can_order and mine[0].total_amount == "229000"

    # Accepting loads the cart at the quoted prices, not the catalogue ones.
    cart = await cart_routes.accept_my_quote(seed.quote_id, db_session, seed.buyer)
    prices = {item.product_id: (item.quantity, item.unit_price) for item in cart.items}
    assert prices == {
        seed.laptop_id: (1, Decimal("140000")),
        seed.screen_id: (2, Decimal("42000")),
    }
    quote = await db_session.get(QuoteRequest, seed.quote_id)
    assert quote is not None
    assert quoted_prices(quote)[seed.screen_id] == (2, Decimal("42000"))

    # Expired → refused; converted → refused (and not re-issuable).
    quote.valid_until = date.today() - timedelta(days=1)
    db_session.add(quote)
    await db_session.commit()
    with pytest.raises(AppError) as expired:
        await cart_routes.accept_my_quote(seed.quote_id, db_session, seed.buyer)
    assert expired.value.code == "quote.expired"
    quote = await db_session.get(QuoteRequest, seed.quote_id)
    assert quote is not None
    quote.valid_until = date.today() + timedelta(days=5)
    quote.order_id = None
    quote.status = QuoteRequestStatus.WON.value
    db_session.add(quote)
    await db_session.commit()
    with pytest.raises(AppError) as won:
        await cart_routes.accept_my_quote(seed.quote_id, db_session, seed.buyer)
    assert won.value.code == "quote.not_issued"


@pytest.mark.asyncio
async def test_a_quote_email_survives_a_missing_pdf_engine(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, sent: list[Any]
) -> None:
    seed = await _seed(db_session)
    monkeypatch.setattr(
        quote_service,
        "render_quote_pdf",
        lambda _quote: (_ for _ in ()).throw(PdfRenderingUnavailableError("no cairo")),
    )
    issued = await issue_quote_request(
        seed.quote_id,
        QuoteIssueBody(
            lines=[
                QuoteLine(
                    product_name="Prestation", quantity=1, unit_price=Decimal("10000")
                )
            ]
        ),
        db_session,
        seed.admin,
    )
    assert issued.email_sent and sent[-1].attachments is None
    # A line without a catalogue product cannot be ordered online.
    mine = await cart_routes.list_my_quotes(db_session, seed.buyer)
    assert not mine[0].can_order
    with pytest.raises(AppError) as offline:
        await cart_routes.accept_my_quote(seed.quote_id, db_session, seed.buyer)
    assert offline.value.code == "quote.not_orderable"
