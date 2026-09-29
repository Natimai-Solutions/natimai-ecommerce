"""Unit: the sellable-stock rule shared by the checkout and the storefront.

``supplier_quantity`` only counts as stock when the product has a supplier;
a warehouse-only product sells from its ``Inventory`` row alone. No database.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.features.inventory.services.availability import (
    has_supplier_stock,
    supplier_available_quantity,
)


def test_synced_product_counts_its_supplier_stock() -> None:
    product = SimpleNamespace(
        is_supplier_managed=True, supplier_name="ingram", supplier_quantity=Decimal("7")
    )
    assert has_supplier_stock(product)
    assert supplier_available_quantity(product) == Decimal("7")


def test_manual_product_linked_to_a_supplier_counts_its_supplier_stock() -> None:
    product = SimpleNamespace(
        is_supplier_managed=False,
        supplier_name="tahiti",
        supplier_quantity=Decimal("3"),
    )
    assert has_supplier_stock(product)
    assert supplier_available_quantity(product) == Decimal("3")


def test_warehouse_only_product_has_no_supplier_stock() -> None:
    """Whatever the column says: without a supplier there is nobody to draw from."""
    for supplier_name in (None, ""):
        product = SimpleNamespace(
            is_supplier_managed=False,
            supplier_name=supplier_name,
            supplier_quantity=Decimal("12"),
        )
        assert not has_supplier_stock(product)
        assert supplier_available_quantity(product) == Decimal("0.00")


def test_missing_supplier_quantity_reads_as_zero() -> None:
    product = SimpleNamespace(
        is_supplier_managed=True, supplier_name="ingram", supplier_quantity=None
    )
    assert supplier_available_quantity(product) == Decimal("0")
