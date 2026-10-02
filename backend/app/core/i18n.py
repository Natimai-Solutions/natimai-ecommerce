"""Language of a request, an order, a customer (R7 / L3).

The storefront sends ``Accept-Language`` with every call; the API answers in
that language (error messages) and freezes it on the order at checkout, so
the e-mails and documents of the order follow the customer's language even
when they are sent later by the worker. A customer's saved preference
(``user_preferences.locale``) wins for the e-mails not tied to an order.
"""

from __future__ import annotations

import contextvars
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import settings

SUPPORTED_LOCALES: tuple[str, ...] = ("fr", "en")

_request_locale: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_locale", default=None
)


def _normalize_many(codes: object, *, first: str | None = None) -> list[str]:
    """Supported, lower-case, unique codes, ``first`` ahead when given."""
    out: list[str] = []
    if first:
        out.append(first)
    for code in codes if isinstance(codes, list | tuple) else []:
        value = normalize_locale(code)
        if value and value not in out:
            out.append(value)
    return out


def default_locale() -> str:
    """The shop's default language (Admin → Paramètres → Affichage, else
    ``SHOP_DEFAULT_LOCALE``): synchronous, from the settings snapshot."""
    from app.core import runtime_settings

    code = normalize_locale(runtime_settings.peek("shop_default_locale"))
    return code or normalize_locale(settings.SHOP_DEFAULT_LOCALE) or "fr"


def offered_locales() -> list[str]:
    """Languages offered to the visitor, default first: synchronous, from the
    settings snapshot (``shop_locales``, else ``SHOP_LOCALES``)."""
    from app.core import runtime_settings

    return _normalize_many(
        runtime_settings.peek("shop_locales"), first=default_locale()
    )


async def get_default_locale(session: Any) -> str:
    """``default_locale`` read from the base (R9 / T2)."""
    from app.core import runtime_settings

    code = normalize_locale(await runtime_settings.get("shop_default_locale", session))
    return code or normalize_locale(settings.SHOP_DEFAULT_LOCALE) or "fr"


async def get_offered_locales(session: Any) -> list[str]:
    """``offered_locales`` read from the base (R9 / T2)."""
    from app.core import runtime_settings

    default = await get_default_locale(session)
    return _normalize_many(
        await runtime_settings.get("shop_locales", session), first=default
    )


def normalize_locale(value: object) -> str | None:
    """``en-GB`` → ``en``; ``None`` when not a supported language."""
    if not isinstance(value, str):
        return None
    base = value.strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LOCALES else None


def from_accept_language(header: str | None) -> str | None:
    """First supported language of an ``Accept-Language`` header (q-values)."""
    if not header:
        return None
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        pieces = [p.strip() for p in part.split(";")]
        tag = pieces[0]
        q = 1.0
        for param in pieces[1:]:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        if tag and q > 0:
            ranked.append((-q, index, tag))
    for _, _, tag in sorted(ranked):
        code = normalize_locale(tag)
        if code:
            return code
    return None


def set_request_locale(code: str | None) -> contextvars.Token[str | None]:
    return _request_locale.set(code)


def reset_request_locale(token: contextvars.Token[str | None]) -> None:
    _request_locale.reset(token)


def request_locale() -> str:
    """Language of the current request (else the shop's default)."""
    return _request_locale.get() or default_locale()


def resolve_locale(*candidates: object) -> str:
    """First supported candidate, else the shop's default."""
    for candidate in candidates:
        code = normalize_locale(candidate)
        if code:
            return code
    return default_locale()


async def user_locale(session: Any, user_id: Any) -> str | None:
    """A customer's saved language, if any."""
    if user_id is None:
        return None
    from app.features.user.crud.user_preference import get_preference_for_user

    try:
        pref = await get_preference_for_user(session, user_id=user_id)
    except Exception:  # noqa: BLE001 - a missing preference is not an error
        return None
    return normalize_locale(getattr(pref, "locale", None))


# --------------------------------------------------------------------------
# Formatting for e-mails and documents (no Babel: two languages, two rules)


def _decimals(currency: str | None) -> int:
    from app.utils.money import currency_decimals

    return currency_decimals(currency)


def format_money(amount: Any, currency: str | None = None, locale: str = "fr") -> str:
    """``12500`` XPF → ``12 500 XPF`` (fr) / ``12,500 XPF`` (en)."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return f"{amount} {currency or ''}".strip()
    places = _decimals(currency)
    text = f"{value:,.{places}f}"
    if locale == "fr":
        text = text.replace(",", " ").replace(".", ",")
    return f"{text} {currency}".strip() if currency else text


def format_date(value: Any, locale: str = "fr") -> str:
    """A date (or datetime) as ``23/06/2026`` (fr) or ``23 Jun 2026`` (en)."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        from datetime import datetime

        text = value
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    fmt = "%d %b %Y" if locale == "en" else "%d/%m/%Y"
    return str(value.strftime(fmt))


__all__ = [
    "SUPPORTED_LOCALES",
    "default_locale",
    "get_default_locale",
    "get_offered_locales",
    "offered_locales",
    "format_date",
    "format_money",
    "from_accept_language",
    "normalize_locale",
    "request_locale",
    "reset_request_locale",
    "resolve_locale",
    "set_request_locale",
    "user_locale",
]
