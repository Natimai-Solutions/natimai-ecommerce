from __future__ import annotations

from app.features.attachment.antivirus.base import AntivirusScanner, ScanResult


class NoOpScanner(AntivirusScanner):
    """Always reports files as clean. Used when CLAMAV_ENABLED is false."""

    async def scan_bytes(self, data: bytes) -> ScanResult:
        return ScanResult(is_clean=True, engine="noop")
