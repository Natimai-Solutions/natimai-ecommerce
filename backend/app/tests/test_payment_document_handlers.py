from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.handlers import payment as handlers
from app.outbox.registry import outbox_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_document_handlers_registered() -> None:
    types = outbox_registry.list_event_types()
    assert "payment.document_required" in types
    assert "payment.document_uploaded" in types
    assert "payment.document_infected" in types


def _make_order() -> Any:
    return SimpleNamespace(id=uuid4(), order_status_id=None)


def _make_status(name: str) -> Any:
    return SimpleNamespace(id=uuid4(), name=name)


def _make_attachment() -> Any:
    return SimpleNamespace(
        id=uuid4(),
        file_key="payments/abc/po.pdf",
        mimetype="application/pdf",
        av_scanned=False,
        av_clean=None,
        av_signature=None,
    )


def _make_payment() -> Any:
    return SimpleNamespace(id=uuid4(), order_id=uuid4(), provider_code="po_public")


@pytest.mark.anyio
async def test_document_required_handler_marks_order_awaiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    order = _make_order()
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))
    status = _make_status("AwaitingPayment")
    monkeypatch.setattr(
        handlers.crud_order_status, "get_by_name", AsyncMock(return_value=status)
    )

    await handlers.on_payment_document_required(
        cast(Any, session),
        {"payment_id": str(uuid4()), "order_id": str(order.id)},
    )

    assert order.order_status_id == status.id


@pytest.mark.anyio
async def test_document_uploaded_handler_runs_av_scan_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    attachment = _make_attachment()
    payment = _make_payment()

    monkeypatch.setattr(
        "app.features.payment.crud.payment_attachment.crud_payment_attachment.read",
        AsyncMock(return_value=attachment),
    )
    monkeypatch.setattr(
        "app.features.payment.crud.payment.crud_payment.read",
        AsyncMock(return_value=payment),
    )

    storage = Mock()
    storage.get_bytes = AsyncMock(return_value=b"%PDF-1.4 clean pdf bytes")
    storage.delete = AsyncMock()
    monkeypatch.setattr(
        "app.features.attachment.storage.factory.get_file_storage",
        lambda: storage,
    )

    scanner = Mock()
    scanner.scan_bytes = AsyncMock(
        return_value=SimpleNamespace(is_clean=True, signature=None)
    )
    monkeypatch.setattr(
        "app.features.attachment.service.get_antivirus_scanner",
        lambda: scanner,
    )

    mark_infected = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.mark_document_infected",
        mark_infected,
    )

    await handlers.on_payment_document_uploaded(
        cast(Any, session),
        {
            "payment_id": str(payment.id),
            "attachment_id": str(attachment.id),
        },
    )

    assert attachment.av_scanned is True
    assert attachment.av_clean is True
    mark_infected.assert_not_awaited()
    storage.delete.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_document_uploaded_handler_quarantines_infected_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()

    attachment = _make_attachment()
    payment = _make_payment()

    monkeypatch.setattr(
        "app.features.payment.crud.payment_attachment.crud_payment_attachment.read",
        AsyncMock(return_value=attachment),
    )
    monkeypatch.setattr(
        "app.features.payment.crud.payment.crud_payment.read",
        AsyncMock(return_value=payment),
    )

    storage = Mock()
    storage.get_bytes = AsyncMock(return_value=b"%PDF-1.4 virus")
    storage.delete = AsyncMock()
    monkeypatch.setattr(
        "app.features.attachment.storage.factory.get_file_storage",
        lambda: storage,
    )

    scanner = Mock()
    scanner.scan_bytes = AsyncMock(
        return_value=SimpleNamespace(is_clean=False, signature="EICAR")
    )
    monkeypatch.setattr(
        "app.features.attachment.service.get_antivirus_scanner",
        lambda: scanner,
    )

    mark_infected = AsyncMock()
    monkeypatch.setattr(
        "app.features.payment.services.document_payment.mark_document_infected",
        mark_infected,
    )

    await handlers.on_payment_document_uploaded(
        cast(Any, session),
        {
            "payment_id": str(payment.id),
            "attachment_id": str(attachment.id),
        },
    )

    storage.delete.assert_awaited_once()
    mark_infected.assert_awaited_once()


@pytest.mark.anyio
async def test_document_uploaded_handler_skips_missing_ids() -> None:
    session = AsyncMock()
    # Just make sure it doesn't crash and doesn't commit
    await handlers.on_payment_document_uploaded(
        cast(Any, session), {"payment_id": None, "attachment_id": None}
    )
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_document_infected_handler_marks_order_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.add = Mock()
    order = _make_order()
    monkeypatch.setattr(handlers.crud_order, "read", AsyncMock(return_value=order))
    status = _make_status("PaymentFailed")
    monkeypatch.setattr(
        handlers.crud_order_status, "get_by_name", AsyncMock(return_value=status)
    )

    await handlers.on_payment_document_infected(
        cast(Any, session),
        {
            "payment_id": str(uuid4()),
            "order_id": str(order.id),
            "attachment_id": str(uuid4()),
            "metadata": {"signature": "EICAR"},
        },
    )

    assert order.order_status_id == status.id
