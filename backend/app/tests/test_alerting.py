"""Webhook alerting (audit I8) — fail-safe contract of ``send_alert``."""

from types import TracebackType
from typing import Any

import pytest

from app.core import alerting
from app.core.config import settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_send_alert_noop_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", None)
    assert await alerting.send_alert("test") is False


@pytest.mark.anyio
async def test_send_alert_posts_slack_style_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "https://hooks.example/x")
    captured: dict[str, Any] = {}

    class _Response:
        status = 200

        async def __aenter__(self) -> "_Response":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            return False

    class _Session:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            return False

        def post(self, url: str, json: dict[str, Any]) -> _Response:
            captured["url"] = url
            captured["json"] = json
            return _Response()

    monkeypatch.setattr("app.core.alerting.aiohttp.ClientSession", _Session)

    assert await alerting.send_alert("outbox dégradé", source="test-suite") is True
    assert captured["url"] == "https://hooks.example/x"
    assert "outbox dégradé" in captured["json"]["text"]
    assert "test-suite" in captured["json"]["text"]


@pytest.mark.anyio
async def test_send_alert_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An alerting failure must never take down the caller."""
    monkeypatch.setattr(settings, "ALERT_WEBHOOK_URL", "https://hooks.example/x")

    class _Boom:
        def __init__(self, **_kwargs: Any) -> None:
            raise RuntimeError("network down")

    monkeypatch.setattr("app.core.alerting.aiohttp.ClientSession", _Boom)

    assert await alerting.send_alert("x") is False
