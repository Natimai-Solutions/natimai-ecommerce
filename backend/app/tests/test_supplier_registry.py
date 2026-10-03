"""Unit tests for the DB-backed supplier registry and the adapter binding."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.suppliers as registry
from app.features.integrations.models.supplier import SupplierKind
from app.services.suppliers import (
    IngramMicroAdapter,
    UnknownAdapterError,
    adapter_for_supplier,
    build_adapter,
    describe_adapters,
    resolve_adapter,
)
from app.services.suppliers.base import SupplierConfig


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _row(
    *,
    code: str = "ingram_micro",
    kind: SupplierKind = SupplierKind.API,
    adapter_key: str | None = "ingram_micro",
    **overrides: object,
) -> SimpleNamespace:
    fields: dict[str, object] = {
        "code": code,
        "name": "Ingram Micro (test)",
        "kind": kind,
        "adapter_key": adapter_key,
        "origin_place_id": uuid.uuid4(),
        "is_domestic": False,
        "sync_enabled": True,
        "sync_interval_hours": 6,
        "default_categories": ["Ordinateur/Serveur"],
        "price_currency": "USD",
        "column_mapping": None,
        "settings": {"environment": "production", "country_code": "US"},
        "is_active": True,
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    registry._INSTANCES.clear()


def test_config_from_row_reads_every_field() -> None:
    row = _row()

    config = SupplierConfig.from_row(row)

    assert config.code == "ingram_micro"
    assert config.display_name == "Ingram Micro (test)"
    assert config.kind == "api"
    assert config.origin_place_id == row.origin_place_id
    assert config.default_categories == ["Ordinateur/Serveur"]
    assert config.settings == {"environment": "production", "country_code": "US"}


def test_ingram_adapter_reads_its_row_settings() -> None:
    adapter = build_adapter(SupplierConfig.from_row(_row()))

    assert isinstance(adapter, IngramMicroAdapter)
    assert adapter.name == "ingram_micro"
    assert adapter.environment == "production"
    assert adapter.country_code == "US"
    assert adapter.service.base_url.endswith("ingrammicro.com:443")
    assert adapter.default_categories == ["Ordinateur/Serveur"]
    assert adapter.sync_interval_hours() == 6
    assert adapter.config_summary()["environment"] == "production"


def test_ingram_adapter_falls_back_to_environment_defaults() -> None:
    adapter = IngramMicroAdapter()

    assert adapter.name == "ingram_micro"
    assert adapter.environment in ("sandbox", "production")
    assert adapter.origin_place_code  # INGRAM_ORIGIN_PLACE_CODE fallback


def test_unknown_adapter_key_is_rejected() -> None:
    with pytest.raises(UnknownAdapterError):
        build_adapter(SupplierConfig(code="x", display_name="X", adapter_key="nope"))


def test_describe_adapters_lists_the_ingram_implementation() -> None:
    described = {d.key: d for d in describe_adapters()}

    assert "ingram_micro" in described
    assert "environment" in described["ingram_micro"].settings_keys


def test_adapter_instances_are_cached_until_the_row_changes() -> None:
    row = _row()
    first = adapter_for_supplier(row)  # type: ignore[arg-type]
    again = adapter_for_supplier(row)  # type: ignore[arg-type]
    assert first is again

    row.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    rebuilt = adapter_for_supplier(row)  # type: ignore[arg-type]
    assert rebuilt is not first


@pytest.mark.anyio
async def test_resolve_adapter_returns_none_for_manual_and_file_suppliers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        registry,
        "load_supplier",
        AsyncMock(return_value=_row(code="generic", kind=SupplierKind.MANUAL)),
    )
    assert await resolve_adapter(AsyncMock(), "generic") is None

    monkeypatch.setattr(
        registry,
        "load_supplier",
        AsyncMock(
            return_value=_row(code="csv", kind=SupplierKind.FILE, adapter_key=None)
        ),
    )
    assert await resolve_adapter(AsyncMock(), "csv") is None


@pytest.mark.anyio
async def test_resolve_adapter_returns_none_for_unknown_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "load_supplier", AsyncMock(return_value=None))

    assert await resolve_adapter(AsyncMock(), "ghost") is None


@pytest.mark.anyio
async def test_resolve_adapter_binds_api_suppliers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(code="ingram_us", is_domestic=False)
    monkeypatch.setattr(registry, "load_supplier", AsyncMock(return_value=row))

    adapter = await resolve_adapter(AsyncMock(), "ingram_us")

    assert adapter is not None
    assert adapter.name == "ingram_us"
    assert adapter.origin_place_id == row.origin_place_id
