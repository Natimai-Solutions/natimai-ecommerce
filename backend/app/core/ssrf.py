"""Outbound requests that may only reach the public Internet (SSRF guard).

An admin-typed URL (supplier feed, outbound webhook) must not reach the
shop's own network: the database, Redis, the cloud metadata endpoint…
Checking the host's addresses *before* the request leaves a window: the
name can resolve to a public address for the check and to 127.0.0.1 for the
connection (DNS rebinding — audit 2026-11). Here the check is the
resolution the connection uses: the addresses are validated, then exactly
those are dialled.
"""

from __future__ import annotations

import asyncio
import errno
import ipaddress
import socket
from typing import Any

import aiohttp
import httpcore
import httpx
from aiohttp.abc import AbstractResolver, ResolveResult


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class PrivateAddressError(OSError):
    """The host resolves (at least partly) into a non-public network."""


async def public_addresses(host: str, port: int) -> list[str]:
    """``host``'s addresses, refused unless every one of them is public."""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not addresses or not all(is_public_address(a) for a in addresses):
        raise PrivateAddressError(
            errno.EACCES, f"Adresse refusée (réseau privé) : {host}"
        )
    return addresses


class _PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """httpcore backend that dials only the validated public addresses (TLS
    still verifies the original host name: httpcore passes it as SNI)."""

    def __init__(self) -> None:
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await public_addresses(host, port)
        except (OSError, socket.gaierror) as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        return await self._inner.connect_tcp(
            addresses[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Any = None
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def public_only_transport() -> httpx.AsyncHTTPTransport:
    """An httpx transport whose connections reach public addresses only."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    transport._pool = httpcore.AsyncConnectionPool(  # noqa: SLF001
        ssl_context=httpx.create_ssl_context(),
        network_backend=_PublicOnlyBackend(),
    )
    return transport


class PublicOnlyResolver(AbstractResolver):
    """aiohttp resolver returning the host's addresses only if all public."""

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        addresses = await public_addresses(host, port)
        return [
            ResolveResult(
                hostname=host,
                host=address,
                port=port,
                family=socket.AF_INET6 if ":" in address else socket.AF_INET,
                proto=0,
                flags=socket.AI_NUMERICHOST,
            )
            for address in addresses
        ]

    async def close(self) -> None:
        return None


def public_only_connector() -> aiohttp.TCPConnector:
    """An aiohttp connector whose connections reach public addresses only."""
    return aiohttp.TCPConnector(resolver=PublicOnlyResolver())
