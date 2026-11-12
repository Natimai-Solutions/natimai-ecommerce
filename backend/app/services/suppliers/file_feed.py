"""A supplier catalogue downloaded from a URL (R4 / S3): Foxway, Picata…

Some wholesalers publish their stock list as a CSV / Excel file behind a
link, sometimes behind a login. This adapter fetches that file on the
supplier's cadence and feeds it through the same column mapping, filters,
thresholds and category rules as a file uploaded by hand.

A supplier using it is declared with ``kind=api`` and ``adapter_key=
"file_feed"``, so it inherits the scheduler ticks and ``sync_interval_hours``.
Its non-secret settings (``Supplier.settings``):

* ``feed_url`` — the file (https only);
* ``auth_mode`` — ``none`` | ``basic`` | ``form``;
* ``login_url``, ``username_field``, ``password_field`` — ``form`` mode: the
  login form is posted first, its cookies are kept for the download;
* ``file_format`` — ``auto`` (from the URL / response) | ``csv`` | ``xlsx``;
* ``sheet_name`` — reserved (the first sheet is read).

Its credentials (``username``, ``password``) are stored encrypted
(:mod:`app.core.secrets_box`) and never leave the server.

Safety: https only, no private / loopback / link-local address (the host is
resolved and checked before every request, redirects included), a size cap
(``SUPPLIER_FEED_MAX_BYTES``) enforced while streaming, a timeout. Out of
scope: portals that need JavaScript or a captcha, and ``.xls`` files.

A feed has no live availability: the checkout keeps the last imported stock
and the 2-hourly inventory refresh skips it (the file brings the stock).
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import AsyncIterator
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import Field

from app.core.config import settings
from app.core.ssrf import is_public_address, public_only_transport
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierHealth,
    SupplierSettings,
)
from app.services.suppliers.file_import import (
    FileImportError,
    read_scanned_tabular_file,
    rows_to_products,
    validate_mapping,
)

logger = logging.getLogger(__name__)

AUTH_MODES = ("none", "basic", "form")
FILE_FORMATS = ("auto", "csv", "xlsx")
MAX_REDIRECTS = 5
#: Products handed to the orchestrator per page.
PAGE_SIZE = 200
#: Bytes read by the health check (enough to see a header line).
HEALTH_PROBE_BYTES = 64 * 1024


class FeedError(RuntimeError):
    """The feed could not be fetched or read (message shown to the admin)."""


def _is_public_address(address: str) -> bool:
    return is_public_address(address)


async def check_public_https_url(url: str) -> None:
    """Refuse anything but https towards a public address (SSRF guard)."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise FeedError(f"Adresse refusée (https obligatoire) : {url}")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise FeedError(f"Hôte introuvable : {parts.hostname}") from exc
    addresses = {str(info[4][0]) for info in infos}
    if not addresses or not all(_is_public_address(a) for a in addresses):
        raise FeedError(f"Adresse refusée (réseau privé) : {parts.hostname}")


class FileFeedSettings(SupplierSettings):
    """``Supplier.settings`` of a file feed (R5 / C4)."""

    feed_url: str | None = Field(
        default=None,
        max_length=1000,
        pattern=r"^[Hh][Tt][Tt][Pp][Ss]://",
        title="Adresse du fichier",
        description="Lien https du fichier catalogue.",
    )
    auth_mode: Literal["none", "basic", "form"] | None = Field(
        default=None, title="Authentification"
    )
    login_url: str | None = Field(
        default=None, max_length=1000, title="Page de connexion (mode formulaire)"
    )
    username_field: str | None = Field(
        default=None, max_length=100, title="Champ identifiant du formulaire"
    )
    password_field: str | None = Field(
        default=None, max_length=100, title="Champ mot de passe du formulaire"
    )
    file_format: Literal["auto", "csv", "xlsx"] | None = Field(
        default=None, title="Format du fichier"
    )
    sheet_name: str | None = Field(default=None, max_length=100, title="Feuille")


class FileFeedAdapter(SupplierAdapter):
    """Catalogue file fetched from a URL, optionally behind a login."""

    adapter_key = "file_feed"
    display_name = "Fichier en ligne (lien)"
    settings_schema = FileFeedSettings
    supports_live_availability = False
    single_source = True
    applies_file_thresholds = True
    #: Tests swap the network for an ``httpx.MockTransport``.
    transport: httpx.AsyncBaseTransport | None = None

    # -- configuration ----------------------------------------------------

    def _setting(self, key: str, default: str = "") -> str:
        value = self.config.settings.get(key)
        return str(value).strip() if value not in (None, "") else default

    @property
    def feed_url(self) -> str:
        return self._setting("feed_url")

    @property
    def auth_mode(self) -> str:
        mode = self._setting("auth_mode", "none").lower()
        return mode if mode in AUTH_MODES else "none"

    @property
    def default_categories(self) -> list[str]:
        # The whole file is one source: a single pseudo-category drives one
        # pass of the orchestrator.
        return ["feed"]

    def configuration_problems(self) -> list[str]:
        problems: list[str] = []
        if not self.feed_url:
            problems.append("feed_url manquant")
        elif not self.feed_url.lower().startswith("https://"):
            problems.append("feed_url doit être en https")
        if self.auth_mode in ("basic", "form"):
            creds = self.config.credentials
            if not creds.get("username") or not creds.get("password"):
                problems.append("identifiants manquants")
        if self.auth_mode == "form" and not self._setting("login_url"):
            problems.append("login_url manquant (mode formulaire)")
        if not self.config.column_mapping:
            problems.append("mapping de colonnes manquant")
        else:
            problems.extend(validate_mapping(self.config.column_mapping))
        return problems

    def is_configured(self) -> bool:
        return not self.configuration_problems()

    # -- download ---------------------------------------------------------

    async def _get(
        self, client: httpx.AsyncClient, url: str, *, limit: int
    ) -> tuple[bytes, str]:
        """GET ``url`` following redirects by hand (each hop checked)."""
        for _ in range(MAX_REDIRECTS + 1):
            await check_public_https_url(url)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FeedError("Redirection sans destination")
                    url = urljoin(url, location)
                    continue
                if response.status_code >= 400:
                    raise FeedError(f"Le serveur a répondu HTTP {response.status_code}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > limit:
                        if limit < settings.SUPPLIER_FEED_MAX_BYTES:
                            chunks.append(chunk)
                            break
                        raise FeedError(
                            f"Fichier trop volumineux (plus de "
                            f"{settings.SUPPLIER_FEED_MAX_BYTES // (1024 * 1024)} Mo)"
                        )
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
                return b"".join(chunks)[:limit], content_type
        raise FeedError("Trop de redirections")

    async def _login(self, client: httpx.AsyncClient) -> None:
        creds = self.config.credentials
        login_url = self._setting("login_url")
        await check_public_https_url(login_url)
        form = {
            self._setting("username_field", "username"): creds.get("username", ""),
            self._setting("password_field", "password"): creds.get("password", ""),
        }
        response = await client.post(login_url, data=form)
        hops = 0
        while response.is_redirect and hops < MAX_REDIRECTS:
            target = urljoin(str(response.url), response.headers.get("location", ""))
            await check_public_https_url(target)
            response = await client.get(target)
            hops += 1
        if response.status_code >= 400:
            raise FeedError(
                f"Connexion refusée par le portail (HTTP {response.status_code})"
            )

    async def download(self, *, limit: int | None = None) -> tuple[bytes, str]:
        """The feed's bytes and a file name telling its format."""
        problems = [p for p in self.configuration_problems() if "mapping" not in p]
        if problems:
            raise FeedError("Flux mal configuré : " + ", ".join(problems))
        cap = limit or int(settings.SUPPLIER_FEED_MAX_BYTES)
        auth: httpx.BasicAuth | None = None
        if self.auth_mode == "basic":
            creds = self.config.credentials
            auth = httpx.BasicAuth(creds.get("username", ""), creds.get("password", ""))
        async with httpx.AsyncClient(
            auth=auth,
            # The default transport dials only validated public addresses:
            # the check and the connection are one resolution (no DNS
            # rebinding window, audit 2026-11).
            transport=self.transport or public_only_transport(),
            follow_redirects=False,
            timeout=httpx.Timeout(float(settings.SUPPLIER_FEED_TIMEOUT_SECONDS)),
            headers={"User-Agent": "catalogue-sync"},
        ) as client:
            try:
                if self.auth_mode == "form":
                    await self._login(client)
                content, content_type = await self._get(
                    client, self.feed_url, limit=cap
                )
            except httpx.HTTPError as exc:
                raise FeedError(f"Téléchargement impossible : {exc}") from exc
        return content, self._file_name(content_type)

    def _file_name(self, content_type: str) -> str:
        wanted = self._setting("file_format", "auto").lower()
        if wanted == "xlsx":
            return "feed.xlsx"
        if wanted == "csv":
            return "feed.csv"
        path = urlsplit(self.feed_url).path.lower()
        if path.endswith(".xls"):
            return "feed.xls"  # refused by the reader, with its explicit message
        if path.endswith((".xlsx", ".xlsm")) or "spreadsheetml" in content_type:
            return "feed.xlsx"
        return "feed.csv"

    # -- contract ---------------------------------------------------------

    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        """The whole file, in pages (``category`` is the pseudo-category)."""
        del category, filters
        content, filename = await self.download()
        try:
            parsed = await read_scanned_tabular_file(content, filename)
        except FileImportError as exc:
            raise FeedError(str(exc)) from exc
        mapping = self.config.column_mapping or {}
        problems = validate_mapping(mapping, parsed.headers)
        if problems:
            raise FeedError("; ".join(problems))
        result = rows_to_products(
            parsed.rows, mapping, default_currency=self.config.price_currency
        )
        if result.errors:
            logger.warning(
                "%s feed: %d unreadable rows (first: row %d, %s)",
                self.name,
                len(result.errors),
                result.errors[0].row_number,
                result.errors[0].message,
            )
        for start in range(0, len(result.products), PAGE_SIZE):
            yield result.products[start : start + PAGE_SIZE]

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        """No live availability: the file is the only source."""
        del skus
        return {}

    async def health_check(self) -> SupplierHealth:
        problems = self.configuration_problems()
        if problems:
            return SupplierHealth(
                healthy=False,
                configured=False,
                message="Flux mal configuré : " + ", ".join(problems),
            )
        try:
            content, filename = await self.download(limit=HEALTH_PROBE_BYTES)
        except FeedError as exc:
            return SupplierHealth(healthy=False, configured=True, message=str(exc))
        return SupplierHealth(
            healthy=True,
            configured=True,
            message="Fichier accessible",
            details={
                "format": filename.rsplit(".", 1)[-1],
                "probe_bytes": len(content),
            },
        )

    async def inspect(self) -> tuple[list[str], list[dict[str, str]], int]:
        """Headers, a few rows and the row count, to build the column mapping."""
        content, filename = await self.download()
        try:
            parsed = await read_scanned_tabular_file(content, filename, max_rows=5)
        except FileImportError as exc:
            raise FeedError(str(exc)) from exc
        return parsed.headers, parsed.rows, parsed.total_rows


__all__ = [
    "AUTH_MODES",
    "FILE_FORMATS",
    "FeedError",
    "FileFeedAdapter",
    "check_public_https_url",
]
