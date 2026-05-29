import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.tasks.supplier_tasks as supplier_tasks


class FakeAdapter:
    def __init__(
        self,
        *,
        name: str,
        sync_enabled: bool,
        configured: bool,
        sync_interval_hours: int,
        price_batch_size: int = 50,
    ) -> None:
        self.name = name
        self._sync_enabled = sync_enabled
        self._configured = configured
        self._sync_interval_hours = sync_interval_hours
        self.price_batch_size = price_batch_size

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def is_configured(self) -> bool:
        return self._configured

    def sync_interval_hours(self) -> int:
        return self._sync_interval_hours

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, SimpleNamespace]:
        return {
            sku: SimpleNamespace(price=100, quantity=5, currency="USD") for sku in skus
        }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_sync_supplier_inventory_task_requires_configured_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter(
        name="ingram_micro",
        sync_enabled=True,
        configured=False,
        sync_interval_hours=6,
    )

    monkeypatch.setattr(supplier_tasks, "has_supplier", lambda _name: True)
    monkeypatch.setattr(supplier_tasks, "get_adapter", lambda _name: adapter)

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={},
        supplier_name=adapter.name,
        skus=None,
    )

    assert result["status"] == "error"
    assert result["message"] == f"Missing {adapter.name} credentials"


@pytest.mark.anyio
async def test_sync_supplier_inventory_task_skips_admin_inactive_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter(
        name="ingram_micro",
        sync_enabled=True,
        configured=True,
        sync_interval_hours=6,
    )

    class _FakeSession:
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

    update_mock = AsyncMock()

    monkeypatch.setattr(supplier_tasks, "has_supplier", lambda _name: True)
    monkeypatch.setattr(supplier_tasks, "get_adapter", lambda _name: adapter)
    monkeypatch.setattr(supplier_tasks, "AsyncSession", _FakeAsyncSession)
    monkeypatch.setattr(
        supplier_tasks.crud_product,
        "get_by_supplier_sku",
        AsyncMock(
            return_value=SimpleNamespace(
                id="prod-1",
                is_admin_active=False,
            )
        ),
    )
    monkeypatch.setattr(supplier_tasks.crud_product, "update", update_mock)

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={},
        supplier_name=adapter.name,
        skus=["SKU-001"],
    )

    assert result["status"] == "success"
    assert result["updated"] == 0
    assert result["errors"] == 0
    update_mock.assert_not_awaited()


def test_get_supplier_sync_cron_jobs_skips_product_sync_when_interval_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter(
        name="demo_supplier",
        sync_enabled=True,
        configured=True,
        sync_interval_hours=0,
    )

    monkeypatch.setattr(supplier_tasks, "all_adapters", lambda: [adapter])

    jobs = supplier_tasks.get_supplier_sync_cron_jobs()
    names = {job.name for job in jobs}

    assert "demo_supplier_product_sync" not in names
    assert "demo_supplier_inventory_sync" in names
    assert "demo_supplier_api_health_check" in names


def test_get_supplier_sync_cron_jobs_adds_product_sync_when_interval_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter(
        name="demo_supplier",
        sync_enabled=True,
        configured=True,
        sync_interval_hours=4,
    )

    monkeypatch.setattr(supplier_tasks, "all_adapters", lambda: [adapter])

    jobs = supplier_tasks.get_supplier_sync_cron_jobs()
    names = {job.name for job in jobs}

    assert "demo_supplier_product_sync" in names
    assert "demo_supplier_inventory_sync" in names
    assert "demo_supplier_api_health_check" in names
