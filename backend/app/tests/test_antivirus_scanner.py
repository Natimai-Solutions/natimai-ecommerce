import io
from unittest.mock import Mock

import pytest

from app.features.attachment.antivirus.base import AntivirusError
from app.features.attachment.antivirus.clamd_scanner import ClamdScanner
from app.features.attachment.antivirus.factory import (
    get_antivirus_scanner,
    reset_antivirus_scanner_cache,
)
from app.features.attachment.antivirus.noop import NoOpScanner


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_noop_scanner_reports_clean() -> None:
    scanner = NoOpScanner()
    result = await scanner.scan_bytes(b"anything")

    assert result.is_clean is True
    assert result.engine == "noop"


@pytest.mark.anyio
async def test_clamd_scanner_returns_clean_for_ok_response() -> None:
    fake_client = Mock()
    fake_client.instream.return_value = {"stream": ("OK", None)}

    scanner = ClamdScanner(host="x", port=3310, client=fake_client)
    result = await scanner.scan_bytes(b"clean data")

    assert result.is_clean is True
    assert result.engine == "clamav"
    fake_client.instream.assert_called_once()
    # First arg passed to instream is a BytesIO
    args, _ = fake_client.instream.call_args
    assert isinstance(args[0], io.BytesIO)


@pytest.mark.anyio
async def test_clamd_scanner_returns_infected_with_signature() -> None:
    fake_client = Mock()
    fake_client.instream.return_value = {"stream": ("FOUND", "EICAR-Test-File")}

    scanner = ClamdScanner(host="x", port=3310, client=fake_client)
    result = await scanner.scan_bytes(b"virus")

    assert result.is_clean is False
    assert result.signature == "EICAR-Test-File"


@pytest.mark.anyio
async def test_clamd_scanner_raises_on_unexpected_response() -> None:
    fake_client = Mock()
    fake_client.instream.return_value = {"stream": ("ERROR", "internal")}

    scanner = ClamdScanner(host="x", port=3310, client=fake_client)
    with pytest.raises(AntivirusError):
        await scanner.scan_bytes(b"x")


def test_factory_returns_noop_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    reset_antivirus_scanner_cache()
    monkeypatch.setattr(settings, "CLAMAV_ENABLED", False)

    scanner = get_antivirus_scanner()
    assert isinstance(scanner, NoOpScanner)
    reset_antivirus_scanner_cache()
