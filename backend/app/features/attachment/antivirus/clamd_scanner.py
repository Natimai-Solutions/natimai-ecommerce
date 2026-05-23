"""ClamAV scanner using the clamd protocol via clamd Python client.

Network I/O is wrapped in a thread executor so the FastAPI worker stays async.
The clamd dependency is imported lazily so test suites without an actual
clamd daemon still work with NoOpScanner.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any, cast

from app.features.attachment.antivirus.base import (
    AntivirusError,
    AntivirusScanner,
    ScanResult,
)


def _build_client(host: str, port: int, timeout: int) -> Any:
    """Build client."""
    try:
        import clamd  # type: ignore[import-untyped]
    except ImportError as e:
        raise AntivirusError(
            "clamd is required for the ClamAV scanner. "
            "Add it to your dependencies (already in pyproject.toml — run `uv sync`)."
        ) from e

    return clamd.ClamdNetworkSocket(host=host, port=port, timeout=timeout)


class ClamdScanner(AntivirusScanner):
    """Represents clamd scanner."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout: int = 30,
        client: Any | None = None,
    ) -> None:
        """Initialize the clamd scanner instance."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self._client = client or _build_client(host, port, timeout)

    async def scan_bytes(self, data: bytes) -> ScanResult:
        """Execute scan bytes."""
        loop = asyncio.get_running_loop()

        def _scan() -> dict[str, tuple[str, str | None]]:
            """Execute scan."""
            return cast(
                dict[str, tuple[str, str | None]],
                self._client.instream(io.BytesIO(data)),
            )

        try:
            result = await loop.run_in_executor(None, _scan)
        except Exception as e:
            raise AntivirusError(f"ClamAV scan failed: {e}") from e

        stream = result.get("stream") if isinstance(result, dict) else None
        if not stream:
            raise AntivirusError(f"Unexpected clamd response: {result!r}")

        status, signature = stream
        if status == "OK":
            return ScanResult(is_clean=True, engine="clamav")
        if status == "FOUND":
            return ScanResult(is_clean=False, signature=signature, engine="clamav")
        raise AntivirusError(f"ClamAV error status: {status} signature={signature}")
