from decimal import Decimal

import pytest

from app.features.integrations.services.supplier_data_normalization import (
    normalize_supplier_snapshot,
)


def test_normalize_supplier_snapshot_rounds_values() -> None:
    snapshot = normalize_supplier_snapshot(
        raw_price="12.345",
        raw_quantity="7.899",
        raw_currency=" xpf ",
    )

    assert snapshot.supplier_price == Decimal("12.35")
    assert snapshot.base_price == Decimal("12.35")
    assert snapshot.supplier_quantity == Decimal("7.90")
    assert snapshot.supplier_price_currency == "XPF"


def test_normalize_supplier_snapshot_defaults_missing_values() -> None:
    snapshot = normalize_supplier_snapshot(
        raw_price=None,
        raw_quantity=None,
        raw_currency=None,
    )

    assert snapshot.supplier_price == Decimal("0.00")
    assert snapshot.base_price == Decimal("0.00")
    assert snapshot.supplier_quantity == Decimal("0.00")
    assert snapshot.supplier_price_currency == "USD"


def test_normalize_supplier_snapshot_rejects_negative_price() -> None:
    with pytest.raises(ValueError):
        normalize_supplier_snapshot(
            raw_price="-1",
            raw_quantity="5",
            raw_currency="USD",
        )


def test_normalize_supplier_snapshot_rejects_invalid_quantity() -> None:
    with pytest.raises(ValueError):
        normalize_supplier_snapshot(
            raw_price="10",
            raw_quantity="abc",
            raw_currency="USD",
        )
