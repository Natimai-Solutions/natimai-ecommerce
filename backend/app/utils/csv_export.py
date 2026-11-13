"""Small helpers for admin CSV downloads (semicolon-separated, Excel-friendly)."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from fastapi import Response

#: A spreadsheet reads a cell starting with these as a formula (``=HYPERLINK``,
#: ``=cmd|…``, ``@SUM``…): a customer name or a credit-note reason typed that
#: way ran in the accountant's Excel (audit 2026-11, S10).
_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
#: Plain numbers (« -12,50 », « +3 ») stay numbers.
_NUMBER = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def safe_cell(value: Any) -> Any:
    """``value`` neutralised for a spreadsheet: a text cell that would be read
    as a formula gets a leading apostrophe (shown as text, OWASP advice)."""
    if not isinstance(value, str) or not value.startswith(_FORMULA_TRIGGERS):
        return value
    if _NUMBER.match(value):
        return value
    return "'" + value


class _SafeWriter:
    """``csv.writer`` whose every cell goes through :func:`safe_cell`."""

    def __init__(self, buffer: io.StringIO) -> None:
        self._writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    def writerow(self, row: Sequence[Any]) -> Any:
        return self._writer.writerow([safe_cell(cell) for cell in row])

    def writerows(self, rows: Iterable[Sequence[Any]]) -> None:
        for row in rows:
            self.writerow(row)


def csv_writer(buffer: io.StringIO) -> _SafeWriter:
    """The admin exports' writer: semicolons, formulas neutralised."""
    return _SafeWriter(buffer)


def csv_amount(value: Decimal | float | int | None) -> str:
    """Amount with a comma decimal separator, as French spreadsheets expect."""
    if value is None:
        return ""
    return f"{Decimal(str(value)):.2f}".replace(".", ",")


def csv_response(
    header: Sequence[str], rows: Iterable[Sequence[Any]], *, filename: str
) -> Response:
    """Build a downloadable CSV response (UTF-8 BOM so Excel reads accents)."""
    buffer = io.StringIO()
    writer = csv_writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
