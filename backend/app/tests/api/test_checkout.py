from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.routes.cart import checkout_my_cart
from app.core.config import settings
from app.core.errors import AppError
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CheckoutRequest
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.payment.crud.payment import crud_payment
from app.features.user.models.user import User


@pytest.fixture(autouse=True)
def _stub_order_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checkout draws its order number from a PostgreSQL sequence (M5).

    These tests run on a mocked session, so the allocation is stubbed here;
    the numbering itself is covered by test_invoice_numbering_and_pdf.py and
    the integration suite.
    """
    monkeypatch.setattr(
        "app.api.routes.cart.allocate_order_number",
        AsyncMock(return_value="CMD-2026-00001"),
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_checkout_creates_order_payment_and_marks_cart_checked_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    order_id = uuid4()
    payment_id = uuid4()
    product_id = uuid4()

    current_user = cast(User, SimpleNamespace(id=user_id))
    session = AsyncMock()
    session.add = Mock()

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        cart_id=cart_id,
        product_id=product_id,
        quantity=2,
        unit_price=Decimal("10.00"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("10.00"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

    order_status = SimpleNamespace(id=uuid4())
    payment_status = SimpleNamespace(id=uuid4())
    order = SimpleNamespace(id=order_id, total_amount=Decimal("0.00"))
    payment = SimpleNamespace(id=payment_id, payment_status_id=None)

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
        "app.api.routes.cart._get_or_create_order_pending_status",
        AsyncMock(return_value=order_status),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        AsyncMock(return_value=None),
    )
    create_order_mock = AsyncMock(return_value=order)
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        create_order_mock,
    )
    monkeypatch.setattr(
        crud_order_line,
        "create_draft",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_payment_pending_status",
        AsyncMock(return_value=payment_status),
    )
    monkeypatch.setattr(
        crud_payment,
        "create_draft",
        AsyncMock(return_value=payment),
    )
    # resolve_default_price_group queries through the raw session, which an
    # AsyncMock cannot serve (result.first() would be a stray coroutine).
    monkeypatch.setattr(
        "app.api.routes.cart.resolve_default_price_group",
        AsyncMock(return_value=None),
    )

    response = await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(
            shipping_address="Papeete", notes="RAS", cgv_accepted=True
        ),
    )

    assert response.order_id == order_id
    assert response.payment_id == payment_id
    assert response.cart_id == cart_id
    assert response.item_count == 1
    assert response.total_amount == Decimal("20")

    assert create_order_mock.await_args is not None
    order_create = create_order_mock.await_args.kwargs["data"]

    assert payment.payment_status_id == payment_status.id
    assert order_create.subtotal_amount == Decimal("20")
    assert order_create.total_fees_amount == Decimal("0")
    assert order_create.total_amount == Decimal("20")
    # Proof of acceptance is snapshotted on the order, not just in the SPA.
    assert order_create.cgv_accepted_at is not None
    assert order_create.cgv_version == settings.CGV_VERSION
    assert cart.is_checked_out is True
    assert item.is_active is False

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_checkout_refuses_without_cgv_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The checkbox in the SPA is not the guard — the API is.

    Nothing must be written: no order, no payment, no stock reservation. The
    refusal happens before the transaction opens.
    """
    user_id = uuid4()
    cart_id = uuid4()
    product_id = uuid4()

    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=user_id))

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        cart_id=cart_id,
        product_id=product_id,
        quantity=2,
        unit_price=Decimal("10.00"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("10.00"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

    monkeypatch.setattr(
        crud_cart, "get_active_cart_by_user", AsyncMock(return_value=cart)
    )
    monkeypatch.setattr(
        crud_cart_item, "get_by_cart_id", AsyncMock(return_value=[item])
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    create_order_mock = AsyncMock()
    monkeypatch.setattr(crud_order, "create_draft", create_order_mock)
    reserve_stock = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout", reserve_stock
    )

    with pytest.raises(AppError) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(shipping_address="Papeete"),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "cart.cgv.not_accepted"
    create_order_mock.assert_not_awaited()
    reserve_stock.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert cart.is_checked_out is False


@pytest.mark.anyio
async def test_checkout_with_payment_method_runs_single_payment_initiation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When payment_method_id is supplied, checkout creates the order AND runs the
    provider initiation in one transaction (no pending placeholder payment)."""
    user_id = uuid4()
    cart_id = uuid4()
    order_id = uuid4()
    payment_id = uuid4()
    product_id = uuid4()
    method_id = uuid4()

    current_user = cast(User, SimpleNamespace(id=user_id, price_group_id=None))
    session = AsyncMock()
    session.add = Mock()

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        cart_id=cart_id,
        product_id=product_id,
        quantity=1,
        unit_price=Decimal("100.00"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("100.00"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )
    order = SimpleNamespace(id=order_id, total_amount=Decimal("0.00"))
    payment = SimpleNamespace(id=payment_id, payment_status_id=uuid4())

    monkeypatch.setattr(
        crud_cart, "get_active_cart_by_user", AsyncMock(return_value=cart)
    )
    monkeypatch.setattr(
        crud_cart_item, "get_by_cart_id", AsyncMock(return_value=[item])
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_order_pending_status",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(crud_order, "create_draft", AsyncMock(return_value=order))
    monkeypatch.setattr(
        crud_order_line,
        "create_draft",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )

    # The placeholder path must NOT be taken.
    placeholder_status = AsyncMock()
    placeholder_payment = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.cart._get_or_create_payment_pending_status",
        placeholder_status,
    )
    monkeypatch.setattr(crud_payment, "create_draft", placeholder_payment)

    init_mock = AsyncMock(
        return_value=SimpleNamespace(
            payment=payment,
            provider_code="manual_check",
            provider_reference="REF-1",
            form_token=None,
            server_url=None,
            public_key=None,
            redirect_url=None,
            instructions="Réglez par chèque à l'ordre de…",
        )
    )
    monkeypatch.setattr("app.api.routes.cart.initiate_payment_for_method", init_mock)
    monkeypatch.setattr(
        "app.api.routes.cart.resolve_default_price_group",
        AsyncMock(return_value=None),
    )

    response = await checkout_my_cart(
        session=session,
        current_user=current_user,
        payload=CheckoutRequest(
            shipping_address="Papeete",
            payment_method_id=method_id,
            cgv_accepted=True,
        ),
    )

    assert response.order_id == order_id
    assert response.payment_id == payment_id
    assert response.provider_code == "manual_check"
    assert response.instructions == "Réglez par chèque à l'ordre de…"

    # Single payment: the provider initiation ran, the placeholder did not.
    init_mock.assert_awaited_once()
    assert init_mock.await_args is not None
    assert init_mock.await_args.kwargs["payment_method_id"] == method_id
    assert init_mock.await_args.kwargs["order_id"] == order_id
    placeholder_status.assert_not_awaited()
    placeholder_payment.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_checkout_rejects_missing_active_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=uuid4()))

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=None),
    )

    with pytest.raises(AppError) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "cart.active.not_found"
    assert exc_info.value.details == {"user_id": str(current_user.id)}


@pytest.mark.anyio
async def test_checkout_rejects_empty_cart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=user_id))
    cart = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=cart),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(AppError) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "cart.empty"
    assert exc_info.value.details == {"cart_id": str(cart.id)}


@pytest.mark.anyio
async def test_checkout_rolls_back_when_stock_reservation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    cart_id = uuid4()
    product_id = uuid4()

    session = AsyncMock()
    session.add = Mock()
    current_user = cast(User, SimpleNamespace(id=user_id))

    cart = SimpleNamespace(
        id=cart_id,
        user_id=user_id,
        currency="XPF",
        total_amount=Decimal("0.00"),
        is_checked_out=False,
    )
    item = SimpleNamespace(
        id=uuid4(),
        cart_id=cart_id,
        product_id=product_id,
        quantity=1,
        unit_price=Decimal("9.99"),
        is_active=True,
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=Decimal("9.99"),
        is_active=True,
        is_admin_active=True,
        is_supplier_managed=False,
        supplier_quantity=Decimal("0.00"),
    )

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
        "app.api.routes.cart._get_or_create_order_pending_status",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        crud_order,
        "create_draft",
        AsyncMock(
            return_value=SimpleNamespace(id=uuid4(), total_amount=Decimal("0.00"))
        ),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._get_active_product_or_404",
        AsyncMock(return_value=product),
    )
    monkeypatch.setattr(
        "app.api.routes.cart._reserve_stock_for_checkout",
        AsyncMock(
            side_effect=AppError(
                code="cart.stock.insufficient",
                status_code=409,
                message="Insufficient stock",
                details={"product_id": str(product_id)},
            )
        ),
    )
    # Reached before the stock reservation raises; queries the raw session,
    # which an AsyncMock cannot serve (result.first() would be a stray coroutine).
    monkeypatch.setattr(
        "app.api.routes.cart.resolve_default_price_group",
        AsyncMock(return_value=None),
    )

    with pytest.raises(AppError) as exc_info:
        await checkout_my_cart(
            session=session,
            current_user=current_user,
            payload=CheckoutRequest(cgv_accepted=True),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "cart.stock.insufficient"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
