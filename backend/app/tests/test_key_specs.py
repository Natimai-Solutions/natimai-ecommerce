"""Key-spec tiles: wording of the values and selection rules (no database)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from app.features.product.models.product_spec import ProductSpec
from app.features.product.services.key_specs import (
    format_numeric,
    format_text,
    select_key_specs,
    tile_label,
)
from app.features.product.services.spec_projection import project_specs_from_payload


def _row(
    key: str,
    *,
    text: str | None = None,
    number: str | None = None,
    unit: str | None = None,
) -> ProductSpec:
    return ProductSpec(
        id=uuid.uuid4(),
        product_id=uuid.uuid4(),
        spec_key=key,
        value_text=text,
        value_numeric=Decimal(number) if number is not None else None,
        unit=unit,
    )


def _def(
    key: str, label: str, rank: int | None, unit: str | None = None
) -> dict[str, Any]:
    return {"key": key, "label_fr": label, "unit": unit, "highlight_rank": rank}


def test_tile_label_drops_the_unit_in_parentheses() -> None:
    assert tile_label("Mémoire RAM (Go)") == "Mémoire RAM"
    assert tile_label("Taille d'écran (pouces)") == "Taille d'écran"
    assert tile_label("Famille de processeur") == "Famille de processeur"


def test_format_numeric_speaks_french() -> None:
    assert format_numeric(Decimal("16.0000"), "GB") == "16 Go"
    assert format_numeric(Decimal("512"), "GB") == "512 Go"
    assert format_numeric(Decimal("1024"), "GB") == "1 To"
    assert format_numeric(Decimal("1536"), "GB") == "1,5 To"
    assert format_numeric(Decimal("15.6000"), "inch") == "15,6 pouces"
    assert format_numeric(Decimal("12"), None) == "12"


def test_format_text_prefers_the_supplier_wording() -> None:
    assert (
        format_text("Intel Core Ultra 5", "intel core ultra 5") == "Intel Core Ultra 5"
    )
    assert format_text(None, "mini-tour") == "Mini-tour"
    assert format_text("  ", None) is None


def test_select_key_specs_follows_rank_and_skips_missing_values() -> None:
    defs = [
        _def("screen_inches", "Taille d'écran (pouces)", 4, "inch"),
        _def("cpu_family", "Famille de processeur", 1),
        _def("memory_gb", "Mémoire RAM (Go)", 2, "GB"),
        _def("storage_gb", "Stockage (Go)", 3, "GB"),
        _def("os", "Système d'exploitation", None),
    ]
    stored = {
        "screen_inches": _row("screen_inches", number="14", unit="inch"),
        "cpu_family": _row("cpu_family", text="intel core ultra 5"),
        # memory_gb missing for this product
        "storage_gb": _row("storage_gb", number="512", unit="GB"),
        "os": _row("os", text="windows 11 pro"),
    }
    tiles = select_key_specs(defs, stored, {"cpu_family": "Intel Core Ultra 5"})

    assert [(t.label, t.value) for t in tiles] == [
        ("Famille de processeur", "Intel Core Ultra 5"),
        ("Stockage", "512 Go"),
        ("Taille d'écran", "14 pouces"),
    ]


def test_select_key_specs_stops_at_the_limit() -> None:
    defs = [_def(f"k{i}", f"Spec {i}", i) for i in range(1, 7)]
    stored = {f"k{i}": _row(f"k{i}", text=f"valeur {i}") for i in range(1, 7)}
    tiles = select_key_specs(defs, stored, {})
    assert [t.key for t in tiles] == ["k1", "k2", "k3", "k4"]


def test_projection_unchanged_by_the_shared_matcher() -> None:
    """The matching loop moved into iter_matched_specs: same results as before."""
    payload = [
        {"name": "Famille de processeur", "value": "Intel Core Ultra 5"},
        {"name": "Mémoire installée", "value": "16 Go"},
        {"name": "Capacité du SSD", "value": "1 TB"},
        {"name": "Taille de l'écran", "value": "35.6 cm"},
        {"name": "Marque inconnue", "value": "ignorée"},
    ]
    projected = project_specs_from_payload(payload, supplier_category="Portable")

    assert projected["cpu_family"] == ("intel core ultra 5", None, None)
    assert projected["memory_gb"][1] == Decimal("16")
    assert projected["storage_gb"][1] == Decimal("1024")
    assert projected["screen_inches"][1] == Decimal("14.0157")
    assert "form_factor" not in projected
