from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.cart import create_quote_request
from app.core.config import settings
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.crud.quote_request import crud_quote_request
from app.features.cart.models.quote_request import QuoteRequestSubmit


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_quote_request_requires_support_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    current_user = SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        full_name="User",
        phone="123456",
    )

    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "")

    with pytest.raises(HTTPException) as exc_info:
        await create_quote_request(
            session=session,
            current_user=current_user,
            payload=QuoteRequestSubmit(),
        )

    assert exc_info.value.status_code == 503


@pytest.mark.anyio
async def test_quote_request_persists_and_notifies_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    item_id = uuid4()
    product_id = uuid4()

    session = AsyncMock()
    current_user = SimpleNamespace(
        id=user_id,
        email="user@example.com",
        full_name="User",
        phone="123456",
    )
    cart = SimpleNamespace(id=cart_id, user_id=user_id, currency="XPF")
    item = SimpleNamespace(
        id=item_id,
        cart_id=cart_id,
        product_id=product_id,
        quantity=2,
        unit_price=Decimal("10.00"),
    )
    product = SimpleNamespace(id=product_id, name="Laptop")
    quote_request = SimpleNamespace(id=uuid4(), status="requested")

    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.com")
    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=cart),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        crud_quote_request,
        "create_draft",
        AsyncMock(return_value=quote_request),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._send_quote_support_email",
        AsyncMock(return_value=True),
    )

    response = await create_quote_request(
        session=session,
        current_user=current_user,
        payload=QuoteRequestSubmit(
            shipping_address="Papeete",
            notes="Merci",
        ),
    )

    assert response.quote_request_id == quote_request.id
    assert response.email_delivered is True
    assert "support notified" in response.message
