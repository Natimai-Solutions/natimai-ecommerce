from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AntivirusError(RuntimeError):
    """Raised when the antivirus engine cannot be reached or fails."""


@dataclass(slots=True)
class ScanResult:
    is_clean: bool
    signature: str | None = None
    engine: str = ""


class AntivirusScanner(ABC):
    @abstractmethod
    async def scan_bytes(self, data: bytes) -> ScanResult: ...
