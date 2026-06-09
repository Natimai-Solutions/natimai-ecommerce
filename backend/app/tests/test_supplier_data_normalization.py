from decimal import Decimal

import pytest

from app.features.integrations.services.supplier_data_normalization import (
    ProductFilterRule,
    evaluate_product_filters,
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


# --- evaluate_product_filters: denylist rules ---------------------------------


def test_filter_rule_skip_matches_subcategory_case_insensitive() -> None:
    rules = [
        ProductFilterRule(
            field="supplier_subcategory",
            values=["Garantie Ordinateur"],
            action="skip",
        )
    ]
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="garantie ordinateur",
        rules=rules,
    )
    assert action == "skip"


def test_filter_rule_no_match_returns_none() -> None:
    rules = [
        ProductFilterRule(field="supplier_subcategory", values=["Garantie Ordinateur"])
    ]
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="Ordinateur de Bureau/Tour",
        rules=rules,
    )
    assert action is None


# --- evaluate_product_filters: subcategory allowlist (curation) ---------------


def test_allowlist_keeps_matching_subcategory() -> None:
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="ordinateur de bureau/tour",
        rules=[],
        subcategory_allowlist=["Ordinateur de Bureau/Tour"],
    )
    assert action is None


def test_allowlist_deactivates_non_matching_subcategory() -> None:
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="Accessoire PC",
        rules=[],
        subcategory_allowlist=["Ordinateur de Bureau/Tour"],
    )
    assert action == "deactivate"


def test_allowlist_deactivates_missing_subcategory() -> None:
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory=None,
        rules=[],
        subcategory_allowlist=["Ordinateur de Bureau/Tour"],
    )
    assert action == "deactivate"


def test_empty_allowlist_is_noop() -> None:
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="Accessoire PC",
        rules=[],
        subcategory_allowlist=[],
    )
    assert action is None


def test_skip_rule_takes_precedence_over_allowlist_deactivate() -> None:
    rules = [
        ProductFilterRule(
            field="name_keyword", values=["extension de garantie"], action="skip"
        )
    ]
    action = evaluate_product_filters(
        supplier_name="ingram_micro",
        supplier_subcategory="Accessoire PC",
        name="Extension de garantie HP 3 ans",
        rules=rules,
        subcategory_allowlist=["Ordinateur de Bureau/Tour"],
    )
    assert action == "skip"
