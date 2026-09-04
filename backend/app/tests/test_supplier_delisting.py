"""Delisting of SKUs the supplier stopped returning.

A product pulled from the supplier catalog used to stay active forever with
its last known price and stock — nothing noticed when Ingram stopped
returning it, so a discontinued reference remained buyable. The rule is
deliberately two-stage: the first absence is only recorded, and the product
is deactivated once the gap outlives the grace period. A transient supplier
fault must never delist the catalog.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.tasks import supplier_tasks

# The helper only ever forwards the session to the (faked) product CRUD.
_NO_SESSION = cast(AsyncSession, None)


class _FakeProduct:
    def __init__(
        self,
        *,
        sku: str,
        missing_since: datetime | None = None,
        is_active: bool = True,
        is_admin_active: bool = True,
    ) -> None:
        self.id = uuid.uuid4()
        self.supplier_sku = sku
        self.supplier_missing_since = missing_since
        self.is_active = is_active
        self.is_admin_active = is_admin_active


class _FakeProductCrud:
    """Minimal stand-in recording the updates the task applies."""

    def __init__(self, products: dict[str, _FakeProduct]) -> None:
        self._products = products
        self.updates: list[tuple[uuid.UUID, dict[str, Any]]] = []

    async def get_by_supplier_sku(
        self, *, session: Any, supplier_sku: str, supplier_name: str, **_kw: Any
    ) -> _FakeProduct | None:
        return self._products.get(supplier_sku)

    async def update(
        self, *, session: Any, id: uuid.UUID, data: Any, record: Any, user: Any
    ) -> Any:
        fields = data.model_dump(exclude_unset=True)
        self.updates.append((id, fields))
        for key, value in fields.items():
            setattr(record, key, value)
        return record


@pytest.fixture
def crud(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install a fake product CRUD and return a factory for seeding it."""
    products: dict[str, _FakeProduct] = {}
    fake = _FakeProductCrud(products)
    monkeypatch.setattr(supplier_tasks, "crud_product", fake)
    fake.seed = products  # type: ignore[attr-defined]
    return fake


@pytest.mark.asyncio
async def test_first_absence_only_flags_it(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One missing response is not proof of a delisting."""
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    crud.seed["GONE"] = _FakeProduct(sku="GONE")

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "STILL-THERE"],
        returned_skus={"STILL-THERE"},
    )

    assert (flagged, delisted) == (1, 0)
    assert crud.seed["GONE"].supplier_missing_since is not None
    assert crud.seed["GONE"].is_active is True


@pytest.mark.asyncio
async def test_absence_within_the_grace_period_changes_nothing(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    flagged_at = datetime.now(timezone.utc) - timedelta(hours=10)
    crud.seed["GONE"] = _FakeProduct(sku="GONE", missing_since=flagged_at)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 0)
    assert crud.seed["GONE"].is_active is True


@pytest.mark.asyncio
async def test_persistent_absence_deactivates_the_product(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    flagged_at = datetime.now(timezone.utc) - timedelta(hours=100)
    crud.seed["GONE"] = _FakeProduct(sku="GONE", missing_since=flagged_at)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 1)
    assert crud.seed["GONE"].is_active is False


@pytest.mark.asyncio
async def test_naive_timestamps_are_read_as_utc(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Postgres hands back naive datetimes; comparing them must not explode."""
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    naive = (datetime.now(timezone.utc) - timedelta(hours=100)).replace(tzinfo=None)
    crud.seed["GONE"] = _FakeProduct(sku="GONE", missing_since=naive)

    _, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert delisted == 1


@pytest.mark.asyncio
async def test_an_empty_response_is_a_fault_not_a_mass_delisting(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fifty SKUs never disappear at once — that is an API problem."""
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    batch = [f"SKU-{i}" for i in range(50)]
    for sku in batch:
        crud.seed[sku] = _FakeProduct(sku=sku)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=batch,
        returned_skus=set(),
    )

    assert (flagged, delisted) == (0, 0)
    assert all(p.supplier_missing_since is None for p in crud.seed.values())


@pytest.mark.asyncio
async def test_grace_period_of_zero_disables_deactivation(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The absence is still recorded, but nothing is ever taken offline."""
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 0)
    flagged_at = datetime.now(timezone.utc) - timedelta(days=365)
    crud.seed["GONE"] = _FakeProduct(sku="GONE", missing_since=flagged_at)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 0)
    assert crud.seed["GONE"].is_active is True


@pytest.mark.asyncio
async def test_admin_disabled_products_are_left_alone(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    crud.seed["GONE"] = _FakeProduct(sku="GONE", is_admin_active=False)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 0)
    assert crud.updates == []


@pytest.mark.asyncio
async def test_an_already_inactive_product_is_not_touched_again(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Idempotence: a delisted product must not be rewritten on every run."""
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)
    flagged_at = datetime.now(timezone.utc) - timedelta(hours=200)
    crud.seed["GONE"] = _FakeProduct(
        sku="GONE", missing_since=flagged_at, is_active=False
    )

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["GONE", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 0)
    assert crud.updates == []


@pytest.mark.asyncio
async def test_nothing_missing_short_circuits(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)

    result = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["A", "B"],
        returned_skus={"A", "B"},
    )

    assert result == (0, 0)
    assert crud.updates == []


@pytest.mark.asyncio
async def test_unknown_sku_is_skipped(
    crud: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A SKU with no local product cannot be delisted."""
    assert crud.seed == {}  # the fixture installs an empty catalog
    monkeypatch.setattr(settings, "SUPPLIER_DELISTING_GRACE_HOURS", 72)

    flagged, delisted = await supplier_tasks._handle_missing_skus(
        _NO_SESSION,
        supplier_name="ingram_micro",
        batch_skus=["NOT-IN-DB", "OK"],
        returned_skus={"OK"},
    )

    assert (flagged, delisted) == (0, 0)
