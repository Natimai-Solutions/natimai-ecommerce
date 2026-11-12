"""Supplier catalogue files: antivirus first, no zip bomb (audit 2026-11)."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from app.services.suppliers import file_import
from app.services.suppliers.file_import import FileImportError


def _xlsx_inflating_to(size: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"\0" * size)
    return buffer.getvalue()


def test_an_xlsx_that_inflates_too_much_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_import, "MAX_XLSX_UNCOMPRESSED_BYTES", 1024 * 1024)
    bomb = _xlsx_inflating_to(5 * 1024 * 1024)
    assert len(bomb) < 50_000  # small on the wire
    with pytest.raises(FileImportError, match="décompressé"):
        file_import.read_tabular_file(bomb, "catalogue.xlsx")


@pytest.mark.asyncio
async def test_an_infected_file_is_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    class Infected:
        async def scan_bytes(self, _data: bytes) -> SimpleNamespace:
            return SimpleNamespace(is_clean=False, signature="Eicar-Test-Signature")

    monkeypatch.setattr(
        "app.features.attachment.antivirus.factory.get_antivirus_scanner",
        lambda: Infected(),
    )
    with pytest.raises(FileImportError, match="antivirus"):
        await file_import.read_scanned_tabular_file(b"sku;price\nA;1\n", "c.csv")
