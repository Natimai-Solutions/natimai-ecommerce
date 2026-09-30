from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.tasks.icecat_tasks as icecat_tasks
from app.features.product.crud.product import crud_product
from app.services.icecat_service import icecat_service


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def icecat_module_on(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The fake sessions cannot be queried: the module switch is stubbed."""
    switch = AsyncMock(return_value=True)
    monkeypatch.setattr(icecat_tasks, "module_enabled", switch)
    return switch


@pytest.mark.anyio
async def test_tasks_do_nothing_while_the_icecat_module_is_off(
    monkeypatch: pytest.MonkeyPatch, icecat_module_on: AsyncMock
) -> None:
    class _FakeAsyncSession:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    icecat_module_on.return_value = False
    enrich = AsyncMock()
    monkeypatch.setattr(icecat_tasks, "AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr(icecat_service, "enrich_product_with_icecat", enrich)

    single = await icecat_tasks.enrich_product_with_icecat_task({}, str(uuid4()))
    batch = await icecat_tasks.batch_enrich_products_task({}, limit=5)

    assert single["status"] == "disabled"
    assert batch["status"] == "disabled"
    enrich.assert_not_awaited()


@pytest.mark.anyio
async def test_enrich_product_with_icecat_task_skips_admin_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product_id = str(uuid4())

    class _FakeSession:
        async def rollback(self) -> None:
            return None

    class _FakeAsyncSession:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._session = _FakeSession()

        async def __aenter__(self) -> _FakeSession:
            return self._session

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _tb: object,
        ) -> bool:
            return False

    enrich_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(icecat_tasks, "AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr(
        crud_product,
        "read",
        AsyncMock(
            return_value=SimpleNamespace(
                id=uuid4(),
                is_admin_active=False,
                vendor_part_number="MPN-123",
                manufacturer="Brand",
            )
        ),
    )
    monkeypatch.setattr(
        icecat_service,
        "enrich_product_with_icecat",
        enrich_mock,
    )

    result = await icecat_tasks.enrich_product_with_icecat_task(
        _ctx={},
        product_id=product_id,
    )

    assert result["status"] == "skipped"
    assert "admin inactive" in result["message"].lower()
    enrich_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_batch_enrich_products_task_skips_admin_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_inactive_product = SimpleNamespace(
        id=uuid4(),
        is_admin_active=False,
        vendor_part_number="SKU-A",
        manufacturer="Brand",
        ean=None,
        supplier_name="Supplier",
    )
    admin_active_product = SimpleNamespace(
        id=uuid4(),
        is_admin_active=True,
        vendor_part_number="SKU-B",
        manufacturer="Brand",
        ean=None,
        supplier_name="Supplier",
    )

    class _ExecResult:
        def __init__(self, rows: list[SimpleNamespace]) -> None:
            self._rows = rows

        def all(self) -> list[SimpleNamespace]:
            return self._rows

    class _FakeSession:
        async def exec(self, _query: object) -> _ExecResult:
            return _ExecResult([admin_inactive_product, admin_active_product])

        async def execute(self, _stmt: object) -> None:
            return None

        async def refresh(self, _product: object) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    class _FakeAsyncSession:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._session = _FakeSession()

        async def __aenter__(self) -> _FakeSession:
            return self._session

        async def __aexit__(
            self,
            _exc_type: object,
            _exc: object,
            _tb: object,
        ) -> bool:
            return False

    enrich_mock = AsyncMock(return_value=None)

    monkeypatch.setattr(icecat_tasks, "AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr(
        icecat_service,
        "enrich_product_with_icecat",
        enrich_mock,
    )
    monkeypatch.setattr(crud_product, "update", AsyncMock())

    result = await icecat_tasks.batch_enrich_products_task(_ctx={}, limit=10)

    assert result["total_processed"] == 2
    assert result["skipped"] == 1
    assert result["not_found"] == 1
    assert result["enriched"] == 0
    assert result["errors"] == 0
    assert enrich_mock.await_count == 1
    # Batch under-filled (2 < 10) → no self re-enqueue.
    assert "requeued" not in result


@pytest.mark.anyio
async def test_batch_enrich_stamps_not_found_and_requeues_when_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full batch stamps each not_found attempt and re-enqueues itself."""
    products = [
        SimpleNamespace(
            id=uuid4(),
            is_admin_active=True,
            vendor_part_number=f"SKU-{i}",
            manufacturer="Brand",
            ean=None,
            supplier_name="Supplier",
        )
        for i in range(2)
    ]

    execute_calls: list[object] = []

    class _ExecResult:
        def all(self) -> list[SimpleNamespace]:
            return products

    class _FakeSession:
        async def exec(self, _query: object) -> _ExecResult:
            return _ExecResult()

        async def execute(self, stmt: object) -> None:
            execute_calls.append(stmt)

        async def refresh(self, _product: object) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    class _FakeAsyncSession:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self._session = _FakeSession()

        async def __aenter__(self) -> _FakeSession:
            return self._session

        async def __aexit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(icecat_tasks, "AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr(
        icecat_service,
        "enrich_product_with_icecat",
        AsyncMock(return_value=None),
    )
    requeue_mock = AsyncMock(return_value="job-next")
    monkeypatch.setattr(icecat_tasks, "trigger_batch_enrichment", requeue_mock)

    result = await icecat_tasks.batch_enrich_products_task(_ctx={}, limit=2)

    assert result["not_found"] == 2
    # Each not_found product was stamped via a direct UPDATE.
    assert len(execute_calls) == 2
    # Full batch (2 >= 2) → re-enqueued exactly once.
    assert result["requeued"] == 1
    requeue_mock.assert_awaited_once_with(limit=2)
