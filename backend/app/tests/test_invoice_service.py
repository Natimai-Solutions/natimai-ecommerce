"""Invoice issuance & tax ventilation (M3).

The critical property is arithmetic: what the invoice prints must add up
exactly to what the customer was charged. These tests pin that invariant on a
fake session so they run without a database.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.features.invoice.services import invoice_service
from app.features.invoice.services.invoice_service import (
    InvoiceIssuanceError,
    _split_incl_tax,
    build_invoice_snapshot,
    issue_invoice_for_order,
)
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.product.models.tax_rate import TaxRate


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows


class _FakeSession:
    """Minimal async session: canned ``exec`` results plus an id-keyed store."""

    def __init__(
        self,
        *,
        objects: dict[Any, Any] | None = None,
        exec_results: list[list[Any]] | None = None,
    ) -> None:
        self.objects = objects or {}
        self._exec_results = exec_results or []
        self.added: list[Any] = []
        self.committed = False

    async def exec(self, _statement: Any) -> _FakeResult:
        rows = self._exec_results.pop(0) if self._exec_results else []
        return _FakeResult(rows)

    async def execute(self, _statement: Any, _params: Any = None) -> Any:
        return SimpleNamespace(scalar_one=lambda: 0)

    async def get(self, _model: Any, key: Any) -> Any:
        return self.objects.get(key)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _obj: Any) -> None:
        return None


def _make_order(**overrides: Any) -> Order:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "order_status_id": uuid.uuid4(),
        "order_number": "CMD-2026-00042",
        "currency": "XPF",
        "subtotal_amount": Decimal("464000"),
        "shipping_fee_amount": Decimal("8700"),
        "payment_fee_amount": Decimal("0"),
        "total_fees_amount": Decimal("8700"),
        "total_amount": Decimal("472700"),
        "shipping_address": "12 rue des Cocotiers, 98713 Papeete",
        "delivery_type": "home_delivery",
    }
    defaults.update(overrides)
    return cast(Order, SimpleNamespace(**defaults))


def _make_tax_rate(rate_pct: str, code: str = "TVA_NORMALE") -> TaxRate:
    return cast(
        TaxRate,
        SimpleNamespace(
            id=uuid.uuid4(),
            code=code,
            label=f"TVA {rate_pct}",
            rate_pct=Decimal(rate_pct),
        ),
    )


def _make_line(
    *, unit_price: str, quantity: int, tax_rate_id: uuid.UUID | None
) -> OrderLine:
    return cast(
        OrderLine,
        SimpleNamespace(
            id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            product_id=uuid.uuid4(),
            quantity=quantity,
            unit_price=Decimal(unit_price),
            discount_amount=Decimal("0"),
            tax_rate_id=tax_rate_id,
        ),
    )


# ---------------------------------------------------------------------------
# Tax split (pure)
# ---------------------------------------------------------------------------


def test_split_incl_tax_is_lossless() -> None:
    """excl + tax must always reconstruct the tax-inclusive amount exactly."""
    for amount in ("472700", "1", "33333", "464000"):
        incl = Decimal(amount)
        excl, tax = _split_incl_tax(incl, Decimal("16.00"), "XPF")
        assert excl + tax == incl


def test_split_incl_tax_at_zero_rate_is_identity() -> None:
    excl, tax = _split_incl_tax(Decimal("5000"), Decimal("0"), "XPF")
    assert (excl, tax) == (Decimal("5000"), Decimal("0"))


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_snapshot_totals_match_the_order_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tax_rate = _make_tax_rate("16.00")
    order = _make_order()
    line = _make_line(unit_price="232000", quantity=2, tax_rate_id=tax_rate.id)

    session = _FakeSession(
        objects={tax_rate.id: tax_rate, line.product_id: SimpleNamespace(name="RTX")},
        exec_results=[[line]],  # order lines
    )
    monkeypatch.setattr(
        invoice_service,
        "_resolve_fees_tax_rate_pct",
        _async_return(Decimal("16.00")),
    )

    snapshot = await build_invoice_snapshot(
        cast(Any, session),
        order=order,
        user=cast(Any, SimpleNamespace(full_name="Jean", email="j@x.pf")),
    )

    totals = snapshot["totals"]
    assert Decimal(totals["incl_tax"]) == order.total_amount
    assert Decimal(totals["excl_tax"]) + Decimal(totals["tax"]) == order.total_amount
    # Product line + fees share the same rate → a single breakdown row.
    assert len(snapshot["tax_breakdown"]) == 1
    assert snapshot["tax_breakdown"][0]["rate_pct"] == "16.00"
    assert snapshot["order"]["number"] == "CMD-2026-00042"


@pytest.mark.anyio
async def test_snapshot_ventilates_several_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    normal = _make_tax_rate("16.00")
    reduced = _make_tax_rate("5.00", code="TVA_REDUITE")
    line_a = _make_line(unit_price="100000", quantity=1, tax_rate_id=normal.id)
    line_b = _make_line(unit_price="50000", quantity=1, tax_rate_id=reduced.id)
    order = _make_order(
        subtotal_amount=Decimal("150000"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
        total_amount=Decimal("150000"),
    )

    session = _FakeSession(
        objects={
            normal.id: normal,
            reduced.id: reduced,
            line_a.product_id: SimpleNamespace(name="A"),
            line_b.product_id: SimpleNamespace(name="B"),
        },
        exec_results=[[line_a, line_b]],
    )
    monkeypatch.setattr(
        invoice_service, "_resolve_fees_tax_rate_pct", _async_return(Decimal("16.00"))
    )

    snapshot = await build_invoice_snapshot(cast(Any, session), order=order, user=None)

    rates = [entry["rate_pct"] for entry in snapshot["tax_breakdown"]]
    assert rates == ["5.00", "16.00"]  # sorted by rate
    assert Decimal(snapshot["totals"]["incl_tax"]) == Decimal("150000")


@pytest.mark.anyio
async def test_snapshot_refuses_to_issue_when_totals_do_not_tie_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A document that does not add up must never be issued."""
    tax_rate = _make_tax_rate("16.00")
    line = _make_line(unit_price="100000", quantity=1, tax_rate_id=tax_rate.id)
    # total_amount inconsistent with subtotal + fees (corrupted order row).
    order = _make_order(
        subtotal_amount=Decimal("100000"),
        shipping_fee_amount=Decimal("0"),
        payment_fee_amount=Decimal("0"),
        total_fees_amount=Decimal("0"),
        total_amount=Decimal("999999"),
    )

    session = _FakeSession(
        objects={tax_rate.id: tax_rate, line.product_id: SimpleNamespace(name="A")},
        exec_results=[[line]],
    )
    monkeypatch.setattr(
        invoice_service, "_resolve_fees_tax_rate_pct", _async_return(Decimal("16.00"))
    )

    with pytest.raises(InvoiceIssuanceError, match="does not match order total"):
        await build_invoice_snapshot(cast(Any, session), order=order, user=None)


# ---------------------------------------------------------------------------
# Issuance
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_issue_invoice_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """A replayed payment.captured must never produce a second invoice."""
    order_id = uuid.uuid4()
    # Annotée Any : voir ci-dessus, la doublure tient lieu d'Invoice.
    existing: Any = SimpleNamespace(invoice_number="FAC-2026-00001", order_id=order_id)
    session = _FakeSession(exec_results=[[existing]])

    allocate = _async_return(("FAC-2026-00002", 2))
    monkeypatch.setattr(invoice_service, "allocate_invoice_number", allocate)

    invoice = await issue_invoice_for_order(cast(Any, session), order_id=order_id)

    assert invoice is existing
    assert session.added == []  # nothing persisted
    assert not session.committed


@pytest.mark.anyio
async def test_issue_invoice_raises_on_unknown_order() -> None:
    session = _FakeSession(exec_results=[[]])  # no existing invoice, no order
    with pytest.raises(InvoiceIssuanceError, match="not found"):
        await issue_invoice_for_order(cast(Any, session), order_id=uuid.uuid4())


def _async_return(value: Any) -> Any:
    """Build an async callable returning ``value`` for any arguments."""

    async def _call(*_args: Any, **_kwargs: Any) -> Any:
        return value

    return _call
