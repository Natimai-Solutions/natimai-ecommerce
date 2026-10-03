"""Per-supplier settings (R5 / C4) and the Icecat tick (C5)."""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.features.integrations.services.supplier_data_normalization import (
    NormalizedSupplierSnapshot,
    meets_sync_thresholds,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    global_filter_action,
)
from app.services.suppliers import ADAPTERS, describe_adapters
from app.tasks.icecat_tasks import _due


def test_each_adapter_declares_a_typed_schema() -> None:
    for descriptor in describe_adapters():
        assert descriptor.settings_schema["type"] == "object"
        assert set(descriptor.settings_keys) == set(
            descriptor.settings_schema["properties"]
        )


def test_schemas_refuse_unknown_keys_and_bad_values() -> None:
    ingram = ADAPTERS["ingram_micro"].settings_schema
    feed = ADAPTERS["file_feed"].settings_schema
    with pytest.raises(ValidationError):
        ingram.model_validate({"environment": "staging"})
    with pytest.raises(ValidationError):
        ingram.model_validate({"made_up": 1})
    with pytest.raises(ValidationError):
        feed.model_validate({"feed_url": "http://plain.example/file.csv"})
    ok = feed.model_validate(
        {"feed_url": "https://x.example/f.csv", "subcategory_allowlist": []}
    )
    assert ok.subcategory_allowlist == []


def test_supplier_filters_replace_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST", ["Laptops"])
    monkeypatch.setattr(settings, "SUPPLIER_PRODUCT_FILTER_RULES", [])
    # Environment: a phone is outside the allowlist.
    assert (
        global_filter_action("s", category="Phones", subcategory="Smartphones")
        == "deactivate"
    )
    # The supplier says « everything »: kept.
    assert (
        global_filter_action(
            "s",
            category="Phones",
            subcategory="Smartphones",
            supplier_settings={"subcategory_allowlist": []},
        )
        is None
    )


def test_supplier_thresholds_replace_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_MIN_QUANTITY", Decimal("0"))
    snapshot = NormalizedSupplierSnapshot(
        supplier_price=Decimal("10"),
        base_price=Decimal("10"),
        supplier_price_currency="USD",
        supplier_quantity=Decimal("2"),
    )
    assert meets_sync_thresholds(snapshot) is True
    assert meets_sync_thresholds(snapshot, min_quantity=Decimal("5")) is False


@pytest.mark.parametrize(
    ("hour", "interval", "due"),
    [(0, 1, True), (5, 1, True), (6, 3, True), (7, 3, False), (5, 0, False)],
)
def test_icecat_tick_due_every_interval(hour: int, interval: int, due: bool) -> None:
    now = datetime.datetime(2026, 10, 1, hour, 15, tzinfo=datetime.UTC)
    assert _due(now, interval) is due
