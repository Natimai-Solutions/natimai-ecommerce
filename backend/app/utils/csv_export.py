"""Small helpers for admin CSV downloads (semicolon-separated, Excel-friendly)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from fastapi import Response


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
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
