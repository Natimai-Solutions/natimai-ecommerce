"""Invoice numbering formats and PDF/HTML rendering (M3), plus order numbers (M5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.features.invoice.models.invoice import Invoice
from app.features.invoice.services.numbering import (
    allocate_invoice_number,
    format_invoice_number,
)
from app.features.invoice.services.pdf import (
    _format_amount,
    render_invoice_html,
)
from app.features.order.services.order_number import (
    format_order_number,
    resolve_order_ref,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Number formats
# ---------------------------------------------------------------------------


def test_invoice_number_format_is_zero_padded() -> None:
    assert format_invoice_number(1, fiscal_year=2026) == "FAC-2026-00001"
    assert format_invoice_number(42, fiscal_year=2026) == "FAC-2026-00042"
    # Beyond the padding width the number simply grows (never truncated).
    assert format_invoice_number(123456, fiscal_year=2026) == "FAC-2026-123456"


def test_order_number_format_is_zero_padded() -> None:
    assert format_order_number(1, year=2026) == "CMD-2026-00001"
    assert format_order_number(42, year=2026) == "CMD-2026-00042"


def test_invoice_and_order_numbers_never_collide() -> None:
    """Two independent counters — the prefixes keep the documents distinct."""
    assert format_invoice_number(7, fiscal_year=2026) != format_order_number(
        7, year=2026
    )


@pytest.mark.anyio
async def test_allocate_invoice_number_increments_and_locks() -> None:
    """The counter row is read FOR UPDATE, then written back incremented."""
    statements: list[str] = []

    class _Session:
        async def execute(self, statement: Any, params: Any = None) -> Any:
            statements.append(" ".join(str(statement).split()))
            return SimpleNamespace(scalar_one=lambda: 41)

    number, sequence_number = await allocate_invoice_number(
        cast(Any, _Session()), fiscal_year=2026
    )

    assert (number, sequence_number) == ("FAC-2026-00042", 42)
    assert "INSERT INTO invoice_counters" in statements[0]
    assert "ON CONFLICT (fiscal_year) DO NOTHING" in statements[0]
    assert "FOR UPDATE" in statements[1]
    assert "UPDATE invoice_counters SET last_value" in statements[2]


# ---------------------------------------------------------------------------
# Order reference resolution (emails)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resolve_order_ref_prefers_payload_number() -> None:
    class _Session:
        async def get(self, *_args: Any) -> Any:  # pragma: no cover - not called
            raise AssertionError("should not hit the database")

    ref = await resolve_order_ref(
        cast(Any, _Session()),
        {"order_number": "CMD-2026-00042", "order_id": str(uuid.uuid4())},
    )
    assert ref == "CMD-2026-00042"


@pytest.mark.anyio
async def test_resolve_order_ref_falls_back_to_short_ref() -> None:
    """Orders predating M5 keep the legacy #abcdef12 reference."""
    order_id = uuid.uuid4()

    class _Session:
        async def get(self, _model: Any, _key: Any) -> Any:
            return SimpleNamespace(order_number=None)

    ref = await resolve_order_ref(cast(Any, _Session()), {"order_id": str(order_id)})
    assert ref == f"#{order_id.hex[:8]}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_format_amount_uses_french_typography() -> None:
    # XPF has no minor unit; thousands use a narrow no-break space.
    assert _format_amount("472700", "XPF") == "472 700 XPF"
    assert _format_amount("1234.5", "EUR") == "1 234,50 EUR"
    assert _format_amount("-5000", "XPF") == "-5 000 XPF"
    # Never raises on unexpected input — a template must not crash.
    assert _format_amount("n/a", "XPF") == "n/a"


def _make_invoice() -> Invoice:
    snapshot: dict[str, Any] = {
        "seller": {
            "name": "Natimai Solutions",
            "address": "BP 123, Papeete",
            "registration": "RC 12345 B",
            "email": "contact@example.pf",
            "phone": "",
            "legal_footer": "Mentions legales",
        },
        "buyer": {
            "name": "Jean Client",
            "email": "jean@example.pf",
            "address": "12 rue des Cocotiers",
        },
        "order": {"id": str(uuid.uuid4()), "number": "CMD-2026-00042"},
        "currency": "XPF",
        "lines": [
            {
                "description": "Carte graphique RTX PRO",
                "reference": "VP-123",
                "quantity": 2,
                "unit_price_incl_tax": "232000",
                "total_incl_tax": "464000",
                "total_excl_tax": "400000",
                "tax_amount": "64000",
                "tax_rate_pct": "16.00",
                "tax_label": "TGC normal",
            }
        ],
        "fees": {
            "shipping_incl_tax": "8700",
            "payment_incl_tax": "0",
            "tax_rate_pct": "16.00",
        },
        "tax_breakdown": [
            {
                "rate_pct": "16.00",
                "base_excl_tax": "407500",
                "tax_amount": "65200",
                "total_incl_tax": "472700",
            }
        ],
        "totals": {"excl_tax": "407500", "tax": "65200", "incl_tax": "472700"},
    }
    return Invoice(
        invoice_number="FAC-2026-00001",
        fiscal_year=2026,
        sequence_number=1,
        order_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        issued_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        currency="XPF",
        total_excl_tax=Decimal("407500"),
        total_tax=Decimal("65200"),
        total_incl_tax=Decimal("472700"),
        snapshot=snapshot,
    )


def test_render_invoice_html_prints_the_snapshot() -> None:
    """The PDF source is the frozen snapshot — never live catalogue data."""
    html = render_invoice_html(_make_invoice())

    assert "FAC-2026-00001" in html
    assert "CMD-2026-00042" in html
    assert "25/08/2026" in html
    assert "Carte graphique RTX PRO" in html
    assert "Jean Client" in html
    assert "Natimai Solutions" in html
    assert "Frais de livraison" in html
    # Amounts formatted through the filter, totals visible.
    assert "472 700 XPF" in html
    # The zero payment fee line is omitted.
    assert "Frais de paiement" not in html


def test_render_invoice_html_escapes_untrusted_values() -> None:
    """Buyer data reaches the template from user input — must be escaped."""
    invoice = _make_invoice()
    invoice.snapshot["buyer"]["name"] = "<script>alert(1)</script>"

    html = render_invoice_html(invoice)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
