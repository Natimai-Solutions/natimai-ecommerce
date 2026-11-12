"""Outbound requests reach public addresses only, checked at connection time
(audit 2026-11: DNS rebinding window of the supplier feed, unguarded
outbound webhook)."""

from __future__ import annotations

import httpx
import pytest

from app.core import ssrf
from app.core.webhook import post_json


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("93.184.216.34", True),
        ("2606:2800:220:1::1", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("169.254.169.254", False),  # cloud metadata
        ("::1", False),
        ("fe80::1%eth0", False),
        ("not-an-ip", False),
    ],
)
def test_public_addresses(address: str, public: bool) -> None:
    assert ssrf.is_public_address(address) is public


@pytest.mark.asyncio
async def test_a_host_resolving_to_a_private_address_is_refused() -> None:
    with pytest.raises(ssrf.PrivateAddressError):
        await ssrf.public_addresses("localhost", 443)


@pytest.mark.asyncio
async def test_the_feed_transport_never_dials_a_private_address() -> None:
    async with httpx.AsyncClient(transport=ssrf.public_only_transport()) as client:
        with pytest.raises(httpx.ConnectError, match="réseau privé"):
            await client.get("https://localhost:9/feed.csv")


@pytest.mark.asyncio
async def test_the_outbound_webhook_never_reaches_the_internal_network() -> None:
    delivered, error = await post_json("https://localhost:9/hook", {"x": 1})
    assert delivered is False
    assert error is not None and "privé" in error


@pytest.mark.asyncio
async def test_the_resolver_hands_aiohttp_only_checked_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(ssrf, "public_addresses", fake)
    results = await ssrf.PublicOnlyResolver().resolve("shop.test", 443)
    assert [r["host"] for r in results] == ["93.184.216.34"]
