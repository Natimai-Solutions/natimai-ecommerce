from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.features.attachment.antivirus.base import AntivirusScanner
from app.features.attachment.antivirus.noop import NoOpScanner


@lru_cache(maxsize=1)
def get_antivirus_scanner() -> AntivirusScanner:
    """Get antivirus scanner."""
    if not settings.CLAMAV_ENABLED:
        return NoOpScanner()

    from app.features.attachment.antivirus.clamd_scanner import ClamdScanner

    return ClamdScanner(
        host=settings.CLAMAV_HOST,
        port=settings.CLAMAV_PORT,
        timeout=settings.CLAMAV_TIMEOUT_SECONDS,
    )


def reset_antivirus_scanner_cache() -> None:
    """Execute reset antivirus scanner cache."""
    get_antivirus_scanner.cache_clear()
