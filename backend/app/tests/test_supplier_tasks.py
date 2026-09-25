from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.tasks.supplier_tasks as supplier_tasks
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.product.crud.product import crud_product


class FakeAdapter:
    def __init__(
        self,
        *,
        name: str,
        sync_enabled: bool,
        configured: bool,
        sync_interval_hours: int,
        price_batch_size: int = 50,
        price_currency: str | None = None,
    ) -> None:
        self.name = name
        self._sync_enabled = sync_enabled
        self._configured = configured
        self._sync_interval_hours = sync_interval_hours
        self.price_batch_size = price_batch_size
        self.price_currency = price_currency
        self.default_categories: list[str] = ["Cat"]
        self.sku_allowlist: list[str] = []

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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _fake_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(supplier_tasks, "AsyncSession", _FakeAsyncSession)


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
    monkeypatch.setattr(
        supplier_tasks, "resolve_adapter", AsyncMock(return_value=adapter)
    )

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={},
        supplier_name=adapter.name,
        skus=None,
    )

    assert result["status"] == "error"
    assert result["message"] == f"Missing {adapter.name} credentials"


@pytest.mark.anyio
async def test_sync_tasks_reject_unknown_or_non_api_suppliers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manual or file supplier resolves to no adapter: nothing to fetch."""
    monkeypatch.setattr(supplier_tasks, "resolve_adapter", AsyncMock(return_value=None))

    inventory = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={}, supplier_name="generic_fr", skus=["SKU-1"]
    )
    catalog = await supplier_tasks.sync_supplier_products_task(
        _ctx={}, supplier_name="generic_fr"
    )

    assert inventory["status"] == "error"
    assert "generic_fr" in inventory["message"]
    assert catalog["status"] == "error"


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
    update_mock = AsyncMock()

    monkeypatch.setattr(
        supplier_tasks, "resolve_adapter", AsyncMock(return_value=adapter)
    )
    monkeypatch.setattr(
        crud_product,
        "get_by_supplier_sku",
        AsyncMock(
            return_value=SimpleNamespace(
                id="prod-1",
                is_admin_active=False,
            )
        ),
    )
    monkeypatch.setattr(crud_product, "update", update_mock)

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={},
        supplier_name=adapter.name,
        skus=["SKU-001"],
    )

    assert result["status"] == "success"
    assert result["updated"] == 0
    assert result["errors"] == 0
    update_mock.assert_not_awaited()


# -- scheduler ticks ---------------------------------------------------------


def test_cron_jobs_are_three_db_driven_ticks() -> None:
    """The supplier list lives in the database: no per-supplier cron at import."""
    jobs = supplier_tasks.get_supplier_sync_cron_jobs()
    names = {job.name for job in jobs}

    assert names == {
        "supplier_catalog_sync_tick",
        "supplier_inventory_sync_tick",
        "supplier_api_health_check_tick",
    }


def test_catalog_sync_due_logic() -> None:
    now = datetime.now(timezone.utc)
    due = supplier_tasks._catalog_sync_due

    assert due(interval_hours=0, last_started_at=None, now=now) is False
    assert due(interval_hours=6, last_started_at=None, now=now) is True
    assert (
        due(interval_hours=6, last_started_at=now - timedelta(hours=2), now=now)
        is False
    )
    assert (
        due(interval_hours=6, last_started_at=now - timedelta(hours=7), now=now) is True
    )
    # Naive timestamps (as stored) are read as UTC.
    naive = (now - timedelta(hours=7)).replace(tzinfo=None)
    assert due(interval_hours=6, last_started_at=naive, now=now) is True


@pytest.mark.anyio
async def test_catalog_tick_enqueues_only_due_enabled_suppliers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(timezone.utc)
    due_adapter = FakeAdapter(
        name="due", sync_enabled=True, configured=True, sync_interval_hours=6
    )
    fresh_adapter = FakeAdapter(
        name="fresh", sync_enabled=True, configured=True, sync_interval_hours=6
    )
    manual_only = FakeAdapter(
        name="manual_only", sync_enabled=True, configured=True, sync_interval_hours=0
    )
    disabled = FakeAdapter(
        name="disabled", sync_enabled=False, configured=True, sync_interval_hours=6
    )
    pairs = [
        (SimpleNamespace(code=a.name), a)
        for a in (due_adapter, fresh_adapter, manual_only, disabled)
    ]
    monkeypatch.setattr(supplier_tasks, "api_suppliers", AsyncMock(return_value=pairs))

    async def _recent(_session: object, **kwargs: object) -> list[SimpleNamespace]:
        if kwargs.get("supplier_name") == "fresh":
            return [SimpleNamespace(started_at=now - timedelta(hours=1))]
        return []

    monkeypatch.setattr(supplier_sync_log_crud, "get_recent_syncs", _recent)
    trigger = AsyncMock(return_value="job-1")
    monkeypatch.setattr(supplier_tasks, "trigger_manual_sync", trigger)

    result = await supplier_tasks.scheduled_supplier_catalog_sync_task({})

    assert result["enqueued"] == ["due"]
    trigger.assert_awaited_once_with("due", categories=["Cat"])


@pytest.mark.anyio
async def test_inventory_tick_enqueues_every_enabled_api_supplier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapters = [
        FakeAdapter(
            name="a", sync_enabled=True, configured=True, sync_interval_hours=0
        ),
        FakeAdapter(
            name="b", sync_enabled=True, configured=False, sync_interval_hours=6
        ),
        FakeAdapter(
            name="c", sync_enabled=True, configured=True, sync_interval_hours=6
        ),
    ]
    pairs = [(SimpleNamespace(code=a.name), a) for a in adapters]
    monkeypatch.setattr(supplier_tasks, "api_suppliers", AsyncMock(return_value=pairs))
    trigger = AsyncMock(return_value="job")
    monkeypatch.setattr(supplier_tasks, "trigger_inventory_refresh", trigger)

    result = await supplier_tasks.scheduled_supplier_inventory_sync_task({})

    # Interval 0 only disables the *catalog* schedule; unconfigured is skipped.
    assert result["enqueued"] == ["a", "c"]


@pytest.mark.anyio
async def test_sync_supplier_inventory_task_never_overwrites_admin_locked_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refurbished lot's quantity (or a negotiated cost) typed in the admin is
    locked; the price/stock sync must leave it alone, as the catalogue sync does."""
    adapter = FakeAdapter(
        name="ingram_micro", sync_enabled=True, configured=True, sync_interval_hours=6
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(
        supplier_tasks, "resolve_adapter", AsyncMock(return_value=adapter)
    )
    monkeypatch.setattr(
        crud_product,
        "get_by_supplier_sku",
        AsyncMock(
            return_value=SimpleNamespace(
                id="prod-1",
                is_admin_active=True,
                overridden_fields=["supplier_quantity", "cost_amount"],
            )
        ),
    )
    monkeypatch.setattr(crud_product, "update", update_mock)
    # No FX table behind the fake session: the threshold check falls back.
    monkeypatch.setattr(
        supplier_tasks,
        "convert_to_reference_currency",
        AsyncMock(return_value=(Decimal("1"), None)),
    )

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={}, supplier_name=adapter.name, skus=["SKU-001"]
    )

    assert result["updated"] == 1
    assert update_mock.await_args is not None
    sent = update_mock.await_args.kwargs["data"].model_dump(exclude_unset=True)
    assert "supplier_quantity" not in sent and "cost_amount" not in sent
    assert sent["supplier_price"] == 100 and sent["supplier_missing_since"] is None


@pytest.mark.anyio
async def test_inventory_refresh_only_asks_for_the_allowlisted_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a SKU allowlist, the price / stock sweep leaves the other
    products of the supplier alone (no request, no update, no delisting)."""
    adapter = FakeAdapter(
        name="ingram_micro", sync_enabled=True, configured=True, sync_interval_hours=6
    )
    adapter.sku_allowlist = ["IM-2"]
    asked: list[list[str]] = []

    async def _fetch(skus: list[str]) -> dict[str, SimpleNamespace]:
        asked.append(list(skus))
        return {s: SimpleNamespace(price=100, quantity=5, currency="USD") for s in skus}

    adapter.fetch_price_and_availability = _fetch  # type: ignore[method-assign]
    monkeypatch.setattr(
        supplier_tasks, "resolve_adapter", AsyncMock(return_value=adapter)
    )
    monkeypatch.setattr(
        crud_product,
        "read_multi",
        AsyncMock(
            return_value={
                "data": [
                    SimpleNamespace(supplier_sku="IM-1"),
                    SimpleNamespace(supplier_sku="IM-2"),
                    SimpleNamespace(supplier_sku="IM-3"),
                ]
            }
        ),
    )
    monkeypatch.setattr(
        crud_product,
        "get_by_supplier_sku",
        AsyncMock(
            return_value=SimpleNamespace(
                id="prod-2", is_admin_active=True, overridden_fields=[]
            )
        ),
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(crud_product, "update", update_mock)
    monkeypatch.setattr(
        supplier_tasks,
        "convert_to_reference_currency",
        AsyncMock(return_value=(Decimal("1"), None)),
    )

    result = await supplier_tasks.sync_supplier_inventory_task(
        _ctx={}, supplier_name=adapter.name, skus=None
    )

    assert asked == [["IM-2"]]
    assert result["total_skus"] == 1 and result["updated"] == 1
