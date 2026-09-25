"""Unit tests for the CSV / Excel catalog import (file suppliers)."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest

from app.services.suppliers.file_import import (
    FileImportError,
    parse_number,
    read_tabular_file,
    rows_to_products,
    validate_mapping,
)

_MAPPING = {
    "supplier_sku": "Référence",
    "name": "Désignation",
    "price": "Prix HT",
    "quantity": "Stock",
    "manufacturer": "Marque",
    "weight": "Poids",
    "subcategory": "Famille",
}


# ---------------------------------------------------------------------------
# parse_number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", Decimal("12")),
        ("12,5", Decimal("12.5")),
        ("12.5", Decimal("12.5")),
        ("1 234,50", Decimal("1234.50")),
        ("1 234,50", Decimal("1234.50")),  # narrow no-break space
        ("1,234.50", Decimal("1234.50")),
        ("1.234,56", Decimal("1234.56")),
        ("12.5 €", Decimal("12.5")),
        ("$1,299.00", Decimal("1299.00")),
        ("", None),
        (None, None),
    ],
)
def test_parse_number_reads_french_and_english_notations(
    raw: str | None, expected: Decimal | None
) -> None:
    assert parse_number(raw) == expected


def test_parse_number_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_number("1.2.3")


# ---------------------------------------------------------------------------
# read_tabular_file
# ---------------------------------------------------------------------------


def test_csv_semicolon_with_bom_and_latin_accents() -> None:
    content = '﻿Référence;Désignation;Prix HT\nA1;Écran 24";199,90\n\n'.encode()

    parsed = read_tabular_file(content, "catalogue.csv")

    assert parsed.headers == ["Référence", "Désignation", "Prix HT"]
    assert parsed.total_rows == 1
    assert parsed.rows[0]["Prix HT"] == "199,90"


def test_csv_windows_1252_is_decoded() -> None:
    content = "Référence;Désignation\nA1;Câble\n".encode("cp1252")

    parsed = read_tabular_file(content, "catalogue.csv")

    assert parsed.rows[0]["Désignation"] == "Câble"


def test_csv_comma_delimited_is_detected() -> None:
    content = b"sku,name,price\nA1,Product A,10.5\nA2,Product B,20\n"

    parsed = read_tabular_file(content, "catalogue.csv")

    assert parsed.headers == ["sku", "name", "price"]
    assert [r["sku"] for r in parsed.rows] == ["A1", "A2"]


def test_max_rows_caps_kept_rows_but_counts_all() -> None:
    content = b"sku;name\n" + b"".join(f"A{i};P{i}\n".encode() for i in range(10))

    parsed = read_tabular_file(content, "catalogue.csv", max_rows=3)

    assert len(parsed.rows) == 3
    assert parsed.total_rows == 10


def test_empty_file_and_legacy_xls_are_refused() -> None:
    with pytest.raises(FileImportError):
        read_tabular_file(b"", "catalogue.csv")
    with pytest.raises(FileImportError):
        read_tabular_file(b"x", "catalogue.xls")


def test_xlsx_first_sheet_is_read() -> None:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Référence", "Désignation", "Prix HT", "Stock"])
    sheet.append(["A1", "Produit A", 1234.5, 3])
    sheet.append([None, None, None, None])
    sheet.append(["A2", "Produit B", 99, 0])
    buffer = io.BytesIO()
    workbook.save(buffer)

    parsed = read_tabular_file(buffer.getvalue(), "catalogue.xlsx")

    assert parsed.headers == ["Référence", "Désignation", "Prix HT", "Stock"]
    assert parsed.total_rows == 2
    assert parsed.rows[0] == {
        "Référence": "A1",
        "Désignation": "Produit A",
        "Prix HT": "1234.5",
        "Stock": "3",
    }


# ---------------------------------------------------------------------------
# validate_mapping
# ---------------------------------------------------------------------------


def test_mapping_requires_sku_and_name() -> None:
    problems = validate_mapping({"price": "Prix"})

    assert any("supplier_sku" in p for p in problems)
    assert any("name" in p for p in problems)


def test_mapping_checks_columns_against_headers() -> None:
    problems = validate_mapping(
        {"supplier_sku": "Ref", "name": "Nom", "bogus": "X"},
        headers=["Ref", "Désignation"],
    )

    assert any("Nom" in p for p in problems)
    assert any("bogus" in p for p in problems)
    assert (
        validate_mapping(
            {"supplier_sku": "Ref", "name": "Désignation"}, ["Ref", "Désignation"]
        )
        == []
    )


# ---------------------------------------------------------------------------
# rows_to_products
# ---------------------------------------------------------------------------


def test_rows_become_normalized_products_with_default_currency() -> None:
    rows = [
        {
            "Référence": "A1",
            "Désignation": "Produit A",
            "Prix HT": "1 234,50",
            "Stock": "3",
            "Marque": "ACME",
            "Poids": "1,2",
            "Famille": "Ordinateur Portable",
        }
    ]

    result = rows_to_products(rows, _MAPPING, default_currency="eur")

    assert result.errors == []
    product = result.products[0]
    assert product.supplier_sku == "A1"
    assert product.name == "Produit A"
    assert product.price == Decimal("1234.50")
    assert product.quantity == Decimal("3")
    assert product.currency == "EUR"
    assert product.weight == 1.2
    assert product.manufacturer == "ACME"
    assert product.subcategory == "Ordinateur Portable"
    assert product.extra == {"source": "file", "row_number": 2}


def test_unreadable_rows_are_reported_not_dropped_silently() -> None:
    rows = [
        {"Référence": "", "Désignation": "Sans ref", "Prix HT": "1"},
        {"Référence": "A2", "Désignation": "Prix cassé", "Prix HT": "1.2.3"},
        {"Référence": "A3", "Désignation": "Négatif", "Stock": "-1"},
        {"Référence": "A4", "Désignation": "OK", "Prix HT": ""},
    ]

    result = rows_to_products(rows, _MAPPING)

    assert [e.row_number for e in result.errors] == [2, 3, 4]
    assert "supplier_sku" in result.errors[0].message
    assert "price" in result.errors[1].message
    assert "quantity" in result.errors[2].message
    assert len(result.products) == 1
    assert result.products[0].price is None
    assert result.products[0].currency is None


# ---------------------------------------------------------------------------
# refurbished lots (condition, grade, battery, licence, warranty, mode)
# ---------------------------------------------------------------------------

_LOT_MAPPING = {
    "supplier_sku": "Réf",
    "name": "Désignation",
    "quantity": "Qté",
    "condition": "État",
    "condition_grade": "Grade",
    "battery_health_pct": "Batterie",
    "os_licence": "Licence",
    "warranty_months": "Garantie",
    "availability_mode": "Mode",
}


def test_refurbished_lot_columns_are_normalized() -> None:
    rows = [
        {
            "Réf": "L1",
            "Désignation": "ThinkPad T14 reconditionné",
            "Qté": "8",
            "État": "Reconditionné",
            "Grade": "a",
            "Batterie": "87",
            "Licence": "Windows 11 Pro",
            "Garantie": "12",
            "Mode": "lot",
        },
        # A new item with no refurbished columns leaves every field None: a
        # re-import never resets what the admin typed.
        {"Réf": "N1", "Désignation": "Souris", "Qté": "50", "État": "neuf"},
    ]

    result = rows_to_products(rows, _LOT_MAPPING)

    assert result.errors == []
    lot, new = result.products
    assert lot.condition == "refurbished"
    assert lot.condition_grade == "A"
    assert lot.battery_health_pct == 87
    assert lot.os_licence == "Windows 11 Pro"
    assert lot.warranty_months == 12
    assert lot.availability_mode == "lot"
    assert new.condition == "new"
    assert (new.condition_grade, new.battery_health_pct, new.availability_mode) == (
        None,
        None,
        None,
    )


def test_refurbished_lot_columns_reject_unknown_values() -> None:
    rows = [
        {"Réf": "B1", "Désignation": "x", "État": "cassé"},
        {"Réf": "B2", "Désignation": "x", "Batterie": "140"},
        {"Réf": "B3", "Désignation": "x", "Garantie": "1,5"},
        {"Réf": "B4", "Désignation": "x", "Mode": "magique"},
    ]

    result = rows_to_products(rows, _LOT_MAPPING)

    assert result.products == []
    assert [e.message.split(" :")[0] for e in result.errors] == [
        "condition",
        "battery_health_pct",
        "warranty_months",
        "availability_mode",
    ]
