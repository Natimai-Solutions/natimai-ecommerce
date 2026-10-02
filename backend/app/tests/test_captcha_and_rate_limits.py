"""R8 / U5 — Turnstile on the public forms and per-IP rate limits."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from fastapi import Request

from app.core import captcha, rate_limit
from app.core.errors import AppError

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _request(headers: dict[str, str] | None = None) -> Request:
    return cast(
        Request,
        SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host="10.0.0.1")),
    )


async def test_captcha_is_a_noop_without_a_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_secret(_session: Any) -> str:
        return ""

    monkeypatch.setattr(captcha, "captcha_secret", no_secret)
    await captcha.require_captcha(_request(), None)  # no token, no error


async def test_captcha_requires_then_verifies_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def secret(_session: Any) -> str:
        return "s3cret"

    seen: list[tuple[str, str, str | None]] = []
    verdict: list[bool | None] = [True]

    async def verify(secret_: str, token: str, ip: str | None) -> bool | None:
        seen.append((secret_, token, ip))
        return verdict[0]

    monkeypatch.setattr(captcha, "captcha_secret", secret)
    monkeypatch.setattr(captcha, "verify_token", verify)

    with pytest.raises(AppError) as missing:
        await captcha.require_captcha(_request(), None)
    assert missing.value.code == "captcha.required"
    assert missing.value.status_code == 400

    await captcha.require_captcha(_request({captcha.TOKEN_HEADER: " tok "}), None)
    assert seen == [("s3cret", "tok", "10.0.0.1")]

    verdict[0] = False
    with pytest.raises(AppError) as failed:
        await captcha.require_captcha(_request({captcha.TOKEN_HEADER: "bad"}), None)
    assert failed.value.code == "captcha.failed"

    # Cloudflare down: fail-open, the rate limits still stand.
    verdict[0] = None
    await captcha.require_captcha(_request({captcha.TOKEN_HEADER: "any"}), None)


async def test_verify_token_survives_a_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, **_kw: Any) -> None: ...

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_a: Any) -> None: ...

        async def post(self, *_a: Any, **_kw: Any) -> Any:
            raise OSError("down")

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    assert await captcha.verify_token("s", "t", "1.2.3.4") is None


async def test_rate_limited_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int, int]] = []
    over: list[bool] = [False]

    async def hit(key: str, *, limit: int, window_seconds: int) -> bool:
        calls.append((key, limit, window_seconds))
        return over[0]

    monkeypatch.setattr(rate_limit, "hit_rate_limit", hit)
    dependency = rate_limit.rate_limited("signup", limit=5, window_seconds=600)
    await dependency(_request())
    assert calls == [("signup:10.0.0.1", 5, 600)]

    over[0] = True
    with pytest.raises(AppError) as exc:
        await dependency(_request())
    assert exc.value.code == "signup.rate_limited"
    assert exc.value.status_code == 429


def test_public_forms_carry_the_guards() -> None:
    """The five routes keep their rate-limit dependency (a refactor that
    drops the decorator argument would silently open the door again)."""
    from app.api.routes import cart, signup, stock_alerts

    def limits(router: Any, path: str) -> set[str]:
        for route in router.routes:
            if getattr(route, "path", None) == path and "POST" in route.methods:
                return {
                    d.call.__qualname__.split(".")[0]
                    for d in route.dependant.dependencies
                    if d.call is not None
                }
        raise AssertionError(path)

    for router, path in (
        (signup.router, "/signup/send-otp"),
        (stock_alerts.router, "/stock-alerts"),
        (cart.router, "/cart/quote-request"),
        (cart.router, "/cart/guest-quote-request"),
        (cart.router, "/cart/checkout"),
    ):
        assert "rate_limited" in limits(router, path), path
