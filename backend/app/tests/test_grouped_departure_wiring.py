"""Unit guards for grouped departures that need no database.

* the checkout attaches the order to the open departure (AST parity check —
  the checkout is too large to drive end to end in a unit test);
* the status validator and the CSV helpers.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.api.routes import cart as cart_module
from app.features.departure.models import (
    DEPARTURE_STATUSES,
    GroupedDepartureCreate,
    check_status,
)
from app.utils.csv_export import csv_amount, csv_response


def _checkout_function() -> ast.AsyncFunctionDef:
    tree = ast.parse(inspect.getsource(cart_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "checkout_my_cart":
            return node
    raise AssertionError("checkout_my_cart not found")


def test_checkout_attaches_the_order_to_the_next_open_departure() -> None:
    fn = _checkout_function()
    awaited = {
        node.value.func.attr
        for node in ast.walk(fn)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
    }
    assert "get_next_open" in awaited

    order_creates = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "OrderCreate"
    ]
    assert order_creates, "the checkout builds the order through OrderCreate"
    for call in order_creates:
        assert "grouped_departure_id" in {kw.arg for kw in call.keywords}


def test_status_validator() -> None:
    for status in DEPARTURE_STATUSES:
        assert check_status(status) == status
    assert check_status(None) is None
    with pytest.raises(ValueError):
        check_status("teleported")
    with pytest.raises(ValueError):
        GroupedDepartureCreate(
            name="x",
            order_cutoff_at=datetime(2026, 10, 15, tzinfo=UTC),
            status="teleported",
        )


def test_csv_helpers() -> None:
    assert csv_amount(Decimal("1234.5")) == "1234,50"
    assert csv_amount(None) == ""
    response = csv_response(["a", "b"], [[1, "é"]], filename="x.csv")
    assert bytes(response.body).decode("utf-8-sig") == "a;b\r\n1;é\r\n"
    assert response.headers["content-disposition"] == 'attachment; filename="x.csv"'
