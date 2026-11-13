"""Admin CSV exports never carry a spreadsheet formula (audit 2026-11, S10)."""

from __future__ import annotations

import io

import pytest

from app.utils.csv_export import csv_response, csv_writer, safe_cell


@pytest.mark.parametrize(
    "typed",
    [
        '=HYPERLINK("https://evil.test","Cliquez")',
        "+33 cmd|' /C calc'!A0",
        "-2+3+cmd|' /C calc'!A0",
        "@SUM(1+1)*cmd|' /C calc'!A0",
        "\t=1+1",
        "\r=1+1",
    ],
)
def test_a_formula_is_turned_into_text(typed: str) -> None:
    assert safe_cell(typed) == "'" + typed


@pytest.mark.parametrize("value", ["-12,50", "+3", "-7", "Tea Vahine", "", 12, None])
def test_numbers_and_plain_text_are_kept(value: object) -> None:
    assert safe_cell(value) == value


def test_every_writer_neutralises_its_cells() -> None:
    buffer = io.StringIO()
    csv_writer(buffer).writerow(["=1+1", "-4,00", "ok"])
    assert buffer.getvalue().strip() == "'=1+1;-4,00;ok"

    response = csv_response(["Nom"], [["=cmd|' /C calc'!A0"]], filename="x.csv")
    body = bytes(response.body).decode("utf-8-sig")
    assert "\n'=cmd" in body.replace("\r\n", "\n")
