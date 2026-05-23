import pytest

import app.tasks.supplier_tasks as supplier_tasks


class FakeAdapter:
    def __init__(
        self,
        *,
        name: str,
        sync_enabled: bool,
        configured: bool,
        sync_interval_hours: int,
    ) -> None:
        self.name = name
        self._sync_enabled = sync_enabled
        self._configured = configured
        self._sync_interval_hours = sync_interval_hours

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def is_configured(self) -> bool:
        return self._configured

    def sync_interval_hours(self) -> int:
        return self._sync_interval_hours


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
