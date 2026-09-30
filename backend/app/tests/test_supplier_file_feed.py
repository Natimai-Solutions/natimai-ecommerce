"""Catalogue files fetched from a supplier URL (R4 / S3)."""

from __future__ import annotations

import socket
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core import secrets_box
from app.core.config import settings
from app.core.errors import AppError
from app.services.suppliers import file_feed
from app.services.suppliers.base import SupplierConfig
from app.services.suppliers.file_feed import FeedError, FileFeedAdapter

CSV = "ref;nom;prix;stock\nF-1;Téléphone A;150,00;4\nF-2;Téléphone B;200;0\n"
MAPPING = {"supplier_sku": "ref", "name": "nom", "price": "prix", "quantity": "stock"}


def _adapter(
    handler: Any,
    *,
    auth_mode: str = "none",
    credentials: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> FileFeedAdapter:
    config = SupplierConfig(
        code="foxway",
        display_name="Foxway",
        adapter_key="file_feed",
        column_mapping=MAPPING,
        price_currency="EUR",
        settings={
            "feed_url": "https://feed.example/stock.csv",
            "auth_mode": auth_mode,
            **(extra or {}),
        },
        credentials=credentials or {},
    )
    adapter = FileFeedAdapter(config)
    adapter.transport = httpx.MockTransport(handler)
    return adapter


@pytest.fixture(autouse=True)
def _public_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test host names do not resolve: the SSRF guard is tested apart."""
    monkeypatch.setattr(file_feed, "check_public_https_url", AsyncMock())


# -- encrypted credentials ------------------------------------------------


def test_credentials_round_trip_and_key_rotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "SUPPLIER_SECRETS_KEY", old)
    token = secrets_box.encrypt_json({"username": "u", "password": "s3cr3t-Pw"})
    assert "s3cr3t" not in token
    assert secrets_box.decrypt_json(token) == {"username": "u", "password": "s3cr3t-Pw"}

    # New key first, old one kept for reading: stored values still decrypt.
    monkeypatch.setattr(settings, "SUPPLIER_SECRETS_KEY", f"{new},{old}")
    assert secrets_box.decrypt_json(token)["password"] == "s3cr3t-Pw"
    # Old key gone: unreadable reads as absent, never raises.
    monkeypatch.setattr(settings, "SUPPLIER_SECRETS_KEY", new)
    assert secrets_box.decrypt_json(token) == {}


def test_no_key_refuses_to_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUPPLIER_SECRETS_KEY", None)
    assert secrets_box.secrets_key_configured() is False
    with pytest.raises(AppError) as refused:
        secrets_box.encrypt_json({"username": "u", "password": "p"})
    assert refused.value.code == "supplier.credentials.no_key"
    assert secrets_box.decrypt_json("anything") == {}


# -- SSRF guard -----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "resolved"),
    [
        ("http://feed.example/x.csv", "93.184.216.34"),
        ("https://localhost/x.csv", "127.0.0.1"),
        ("https://intranet.example/x.csv", "10.0.0.5"),
        ("https://meta.example/x.csv", "169.254.169.254"),
        ("https://v6.example/x.csv", "::1"),
    ],
)
async def test_guard_refuses_plain_http_and_private_networks(
    monkeypatch: pytest.MonkeyPatch, url: str, resolved: str
) -> None:
    async def fake_resolve(*_args: Any, **_kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (resolved, 443))]

    loop = __import__("asyncio").get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_resolve)
    with pytest.raises(FeedError):
        await _real_guard(url)


@pytest.mark.asyncio
async def test_guard_accepts_a_public_https_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve(*_args: Any, **_kwargs: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443))]

    loop = __import__("asyncio").get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_resolve)
    await _real_guard("https://feed.example/x.csv")


_GUARD = file_feed.check_public_https_url


async def _real_guard(url: str) -> None:
    await _GUARD(url)


# -- download and parsing -------------------------------------------------


@pytest.mark.asyncio
async def test_catalogue_is_read_through_the_mapping() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, text=CSV))
    pages = [page async for page in adapter.fetch_catalog("feed")]
    (products,) = pages
    assert [p.supplier_sku for p in products] == ["F-1", "F-2"]
    assert products[0].price == Decimal("150.00")
    assert products[0].currency == "EUR"
    assert adapter.is_configured() is True
    assert adapter.supports_live_availability is False
    assert await adapter.fetch_price_and_availability(["F-1"]) == {}


@pytest.mark.asyncio
async def test_basic_auth_is_sent() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(200, text=CSV)

    adapter = _adapter(
        handler, auth_mode="basic", credentials={"username": "u", "password": "p"}
    )
    await adapter.download()
    assert seen[0].startswith("Basic ")


@pytest.mark.asyncio
async def test_form_login_then_download_with_its_cookie() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            assert b"email=u" in request.content
            return httpx.Response(
                302,
                headers={"location": "/home", "set-cookie": "session=ok; Path=/"},
            )
        if request.url.path == "/home":
            return httpx.Response(200, text="welcome")
        if request.headers.get("cookie") != "session=ok":
            return httpx.Response(403)
        return httpx.Response(302, headers={"location": "/files/stock.csv"})

    def final(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/files/stock.csv":
            return httpx.Response(200, text=CSV)
        return handler(request)

    adapter = _adapter(
        final,
        auth_mode="form",
        credentials={"username": "u", "password": "p"},
        extra={
            "login_url": "https://feed.example/login",
            "username_field": "email",
            "password_field": "pwd",
        },
    )
    content, name = await adapter.download()
    assert content.decode() == CSV
    assert name == "feed.csv"


@pytest.mark.asyncio
async def test_errors_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    denied = _adapter(lambda request: httpx.Response(401))
    with pytest.raises(FeedError, match="HTTP 401"):
        await denied.download()

    monkeypatch.setattr(settings, "SUPPLIER_FEED_MAX_BYTES", 10)
    big = _adapter(lambda request: httpx.Response(200, text=CSV))
    with pytest.raises(FeedError, match="volumineux"):
        await big.download()

    no_login = _adapter(lambda request: httpx.Response(200), auth_mode="basic")
    assert "identifiants manquants" in no_login.configuration_problems()
    with pytest.raises(FeedError, match="identifiants"):
        await no_login.download()


@pytest.mark.asyncio
async def test_xls_is_refused_with_a_clear_message() -> None:
    adapter = _adapter(
        lambda request: httpx.Response(200, content=b"\xd0\xcf\x11\xe0"),
        extra={"feed_url": "https://feed.example/stock.xls"},
    )
    with pytest.raises(FeedError, match="xls"):
        [page async for page in adapter.fetch_catalog("feed")]


@pytest.mark.asyncio
async def test_health_probe_reads_only_the_start() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, text=CSV * 5000))
    health = await adapter.health_check()
    assert health.healthy is True
    assert health.details["probe_bytes"] <= file_feed.HEALTH_PROBE_BYTES
