"""Unit tests for the Ingram Micro purchase-order creation service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.features.integrations.services.supplier_order_service as svc
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.services.suppliers.ingram_micro import IngramMicroService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _session() -> MagicMock:
    """A fake AsyncSession: sync ``add``, awaitable ``commit`` / ``refresh``."""
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture(autouse=True)
def _isolate_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default: no pre-existing supplier order, ship-to configured.
    monkeypatch.setattr(
        svc, "get_existing_supplier_order", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        svc,
        "build_ship_to",
        lambda: {"addressLine1": "1 warehouse", "city": "Papeete", "countryCode": "PF"},
    )


@pytest.mark.anyio
async def test_skips_when_no_ingram_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "build_ingram_lines", AsyncMock(return_value=[]))
    create_spy = AsyncMock()
    monkeypatch.setattr(IngramMicroService, "create_purchase_order", create_spy)

    result = await svc.process_ingram_purchase_order(_session(), uuid.uuid4())

    assert result is not None
    assert result.status == SupplierOrderStatus.SKIPPED
    create_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_errors_when_ship_to_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        svc, "build_ingram_lines", AsyncMock(return_value=[{"ingramPartNumber": "A"}])
    )
    monkeypatch.setattr(svc, "build_ship_to", lambda: None)
    create_spy = AsyncMock()
    monkeypatch.setattr(IngramMicroService, "create_purchase_order", create_spy)

    result = await svc.process_ingram_purchase_order(_session(), uuid.uuid4())

    assert result is not None
    assert result.status == SupplierOrderStatus.ERROR
    assert "SHIP_TO" in (result.error_message or "")
    create_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_submits_and_records_po(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        svc,
        "build_ingram_lines",
        AsyncMock(return_value=[{"ingramPartNumber": "ABC", "quantity": 2}]),
    )
    monkeypatch.setattr(
        IngramMicroService,
        "create_purchase_order",
        AsyncMock(
            return_value={"ingramOrderNumber": "IM-999", "orderStatus": "Accepted"}
        ),
    )

    result = await svc.process_ingram_purchase_order(_session(), uuid.uuid4())

    assert result is not None
    assert result.status == SupplierOrderStatus.SUBMITTED
    assert result.supplier_order_number == "IM-999"
    assert result.supplier_status_label == "Accepted"


@pytest.mark.anyio
async def test_already_submitted_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SupplierOrder(
        supplier_name="ingram_micro",
        local_order_id=uuid.uuid4(),
        customer_order_number="x",
        status=SupplierOrderStatus.SUBMITTED,
        supplier_order_number="IM-1",
    )
    monkeypatch.setattr(
        svc, "get_existing_supplier_order", AsyncMock(return_value=existing)
    )
    lines_spy = AsyncMock()
    monkeypatch.setattr(svc, "build_ingram_lines", lines_spy)
    create_spy = AsyncMock()
    monkeypatch.setattr(IngramMicroService, "create_purchase_order", create_spy)

    result = await svc.process_ingram_purchase_order(_session(), uuid.uuid4())

    assert result is existing
    lines_spy.assert_not_awaited()
    create_spy.assert_not_awaited()


@pytest.mark.anyio
async def test_api_error_reraises_for_outbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        svc,
        "build_ingram_lines",
        AsyncMock(return_value=[{"ingramPartNumber": "ABC", "quantity": 1}]),
    )
    monkeypatch.setattr(
        IngramMicroService,
        "create_purchase_order",
        AsyncMock(side_effect=RuntimeError("ingram 503")),
    )

    with pytest.raises(RuntimeError, match="ingram 503"):
        await svc.process_ingram_purchase_order(
            _session(), uuid.uuid4(), reraise_on_api_error=True
        )


@pytest.mark.anyio
async def test_api_error_returns_error_record_for_admin_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc,
        "build_ingram_lines",
        AsyncMock(return_value=[{"ingramPartNumber": "ABC", "quantity": 1}]),
    )
    monkeypatch.setattr(
        IngramMicroService,
        "create_purchase_order",
        AsyncMock(side_effect=RuntimeError("ingram 503")),
    )

    result = await svc.process_ingram_purchase_order(
        _session(), uuid.uuid4(), reraise_on_api_error=False
    )

    assert result is not None
    assert result.status == SupplierOrderStatus.ERROR
    assert "ingram 503" in (result.error_message or "")
