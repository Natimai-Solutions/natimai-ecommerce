from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.features.product.crud.product import ProductCrud


def _product(manufacturer: str | None, *, base_price: str = "10000") -> Any:
    return SimpleNamespace(
        manufacturer=manufacturer,
        category_id=None,
        base_price=Decimal(base_price),
    )


def test_manufacturer_facet_groups_case_insensitively() -> None:
    products = [
        _product("HP Inc."),
        _product("HP INC."),
        _product("hp inc."),
        _product("Dell"),
    ]

    facets = ProductCrud._build_search_facets(products)

    manufacturers = facets["manufacturers"]
    # The three HP spellings collapse into one facet with the first-seen label.
    assert manufacturers["HP Inc."] == 3
    assert "HP INC." not in manufacturers
    assert manufacturers["Dell"] == 1


def test_manufacturer_facet_handles_missing_manufacturer() -> None:
    products = [_product(None), _product("  "), _product("Dell")]

    facets = ProductCrud._build_search_facets(products)

    assert facets["manufacturers"]["unknown"] == 2
    assert facets["manufacturers"]["Dell"] == 1


def test_price_range_buckets() -> None:
    products = [
        _product("A", base_price="0"),
        _product("A", base_price="49999"),
        _product("A", base_price="50000"),
        _product("A", base_price="100000"),
    ]

    facets = ProductCrud._build_search_facets(products)

    assert facets["price_ranges"] == {
        "0-49999": 2,
        "50000-99999": 1,
        "100000+": 1,
    }
    # category_id None collapses to the "none" bucket
    assert facets["categories"]["none"] == 4
