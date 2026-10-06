"""Payment service providers switched on and off from the database (R3-P5).

The manual methods (cash, cheque, transfer, purchase order) are driven by
their ``payment_methods`` row (``is_admin_active``). The card and wallet
providers get an extra switch per provider, so the shop can turn PayZen,
PayPal or Stripe off — maintenance, a contract that ends, a test — without a
deployment and without touching the payment methods that point at them.

A provider is **available** when it is switched on *and* its credentials are
present in the environment. An unavailable provider disappears from the
checkout, refuses new payments, and still receives the notifications of the
payments it already started (money must never be lost to a switch).

The switch lives in ``system_settings`` (``payment_provider_<code>_enabled``),
declared in the runtime settings registry (R5).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.system.models.system_setting import SystemSetting

#: Providers with a switch, in display order, and their default state.
PSP_DEFAULTS: dict[str, bool] = {"payzen": True, "paypal": False, "stripe": False}
PSP_LABELS: dict[str, str] = {
    "payzen": "PayZen (carte bancaire)",
    "paypal": "PayPal",
    "stripe": "Stripe",
}
#: Implemented in this code base (Stripe is planned, R3-P6).
IMPLEMENTED: frozenset[str] = frozenset({"payzen", "paypal"})

_TRUE = {"true", "1", "yes", "oui", "on"}
_FALSE = {"false", "0", "no", "non", "off"}


def setting_key(provider_code: str) -> str:
    return f"payment_provider_{provider_code}_enabled"


def credentials_present(provider_code: str) -> bool:
    """Whether the environment holds what the provider needs to take money."""
    if provider_code == "payzen":
        password = (
            settings.PAYZEN_API_PASSWORD_PROD
            if settings.PAYZEN_MODE == "PRODUCTION"
            else settings.PAYZEN_API_PASSWORD_TEST
        )
        return bool(settings.PAYZEN_SITE_ID and password)
    if provider_code == "paypal":
        return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET)
    return False


def _parse(raw: str | None, default: bool) -> bool:
    value = (raw or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return default


async def switches(session: AsyncSession, *, fresh: bool = False) -> dict[str, bool]:
    """The on/off state of every provider with a switch, in one query.

    ``fresh=True`` bypasses this process's settings snapshot (the back-office
    re-reading what it just saved, possibly through another API worker); the
    checkout keeps the snapshot.
    """
    from app.core import runtime_settings

    values = await runtime_settings.get_many(
        [setting_key(code) for code in PSP_DEFAULTS], session, fresh=fresh
    )
    return {code: bool(values[setting_key(code)]) for code in PSP_DEFAULTS}


def _available(code: str, state: dict[str, bool]) -> bool:
    if code not in PSP_DEFAULTS:
        return True  # manual / document methods: their payment_methods row rules
    return state[code] and code in IMPLEMENTED and credentials_present(code)


async def provider_available(session: AsyncSession, provider_code: str) -> bool:
    code = provider_code.strip().lower()
    if code not in PSP_DEFAULTS:
        return True
    return _available(code, await switches(session))


async def unavailable_providers(
    session: AsyncSession, provider_codes: Iterable[str]
) -> set[str]:
    """The subset of ``provider_codes`` that cannot take a new payment now."""
    codes = {code.strip().lower() for code in provider_codes}
    if not codes & set(PSP_DEFAULTS):
        return set()
    state = await switches(session)
    return {code for code in codes if not _available(code, state)}


@dataclass(frozen=True)
class ProviderState:
    code: str
    label: str
    enabled: bool
    credentials_present: bool
    implemented: bool

    @property
    def available(self) -> bool:
        return self.enabled and self.implemented and self.credentials_present


async def provider_states(
    session: AsyncSession, *, fresh: bool = False
) -> list[ProviderState]:
    state = await switches(session, fresh=fresh)
    return [
        ProviderState(
            code=code,
            label=PSP_LABELS[code],
            enabled=state[code],
            credentials_present=credentials_present(code),
            implemented=code in IMPLEMENTED,
        )
        for code in PSP_DEFAULTS
    ]


async def set_provider_enabled(
    session: AsyncSession, provider_code: str, enabled: bool
) -> None:
    """Switch a provider on or off. Flushes, no commit."""
    key = setting_key(provider_code)
    row = (
        await session.exec(select(SystemSetting).where(col(SystemSetting.key) == key))
    ).first()
    value = "true" if enabled else "false"
    if row is None:
        row = SystemSetting(
            key=key, value=value, description=_description(provider_code)
        )
    else:
        row.value = value
    session.add(row)
    await session.flush()


def _description(provider_code: str) -> str:
    return (
        f"Prestataire {PSP_LABELS.get(provider_code, provider_code)} activé "
        "(true / false) — les identifiants restent dans l'environnement"
    )


def seed_rows() -> list[SystemSetting]:
    """The switch rows, at their default value, for the initial data seed."""
    return [
        SystemSetting(
            key=setting_key(code),
            value="true" if default else "false",
            description=_description(code),
        )
        for code, default in PSP_DEFAULTS.items()
    ]


__all__ = [
    "IMPLEMENTED",
    "PSP_DEFAULTS",
    "PSP_LABELS",
    "ProviderState",
    "credentials_present",
    "provider_available",
    "provider_states",
    "set_provider_enabled",
    "seed_rows",
    "setting_key",
    "switches",
    "unavailable_providers",
]
