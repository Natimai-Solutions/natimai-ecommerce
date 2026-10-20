"""Which tax rate applies by default, and which one taxes the fees.

The rates themselves are rows of ``tax_rates`` the admin creates freely (code,
label, percentage, territory, validity). Two choices complete them, stored in
``system_settings`` and editable from the admin:

* ``tax_default_code`` — the rate of a product whose product and category say
  nothing;
* ``tax_fees_code`` — the rate of the shipping / payment / deposit fees on the
  invoice.

Both name a rate *code*: a rate closed and replaced by a new one under the same
code (a change of percentage) keeps being the default. Without a setting, the
environment (``DEFAULT_TAX_CODE`` / ``INVOICE_FEES_TAX_CODE``, filled by the
territory profile) is the starting point.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.system.models.system_setting import SystemSetting

DEFAULT_CODE_KEY = "tax_default_code"
FEES_CODE_KEY = "tax_fees_code"

#: Codes of the first Polynesian seed, renamed « TVA » (the Polynesian tax is
#: the TVA; « TGC » is the Caledonian one). An environment still naming them
#: keeps working.
LEGACY_CODES: dict[str, str] = {
    "TGC_NORMAL": "TVA_NORMALE",
    "TGC_REDUIT": "TVA_REDUITE",
    "TGC_EXONERE": "TVA_EXONEREE",
}


def normalize_code(code: str | None) -> str:
    value = (code or "").strip().upper()
    return LEGACY_CODES.get(value, value)


@dataclass(frozen=True)
class TaxCodes:
    default_code: str
    fees_code: str


async def load_tax_codes(session: AsyncSession, *, fresh: bool = False) -> TaxCodes:
    """The default and fees rate codes: the admin's choice, else the env
    (runtime registry).

    ``fresh=True`` reads the base instead of this process's snapshot: for the
    back-office, which must show what it just saved even when another API
    worker took the write (see :mod:`app.core.runtime_settings`). Pricing and
    invoicing keep the snapshot.
    """
    from app.core import runtime_settings

    values = await runtime_settings.get_many(
        [DEFAULT_CODE_KEY, FEES_CODE_KEY], session, fresh=fresh
    )
    return TaxCodes(
        default_code=normalize_code(
            values[DEFAULT_CODE_KEY] or settings.DEFAULT_TAX_CODE
        ),
        fees_code=normalize_code(
            values[FEES_CODE_KEY] or settings.INVOICE_FEES_TAX_CODE
        ),
    )


async def save_tax_codes(
    session: AsyncSession, *, default_code: str, fees_code: str
) -> TaxCodes:
    """Store both choices. Flushes, no commit."""
    descriptions = {
        DEFAULT_CODE_KEY: (
            "Code du taux de TVA appliqué quand ni l'article ni sa catégorie "
            "n'en précisent"
        ),
        FEES_CODE_KEY: (
            "Code du taux de TVA des frais (livraison, paiement, acompte) sur "
            "les factures"
        ),
    }
    values = {
        DEFAULT_CODE_KEY: normalize_code(default_code),
        FEES_CODE_KEY: normalize_code(fees_code),
    }
    existing = {
        row.key: row
        for row in (
            await session.exec(
                select(SystemSetting).where(col(SystemSetting.key).in_(list(values)))
            )
        ).all()
    }
    for key, value in values.items():
        row = existing.get(key) or SystemSetting(
            key=key, value=value, description=descriptions[key]
        )
        row.value = value
        session.add(row)
    await session.flush()
    return TaxCodes(
        default_code=values[DEFAULT_CODE_KEY], fees_code=values[FEES_CODE_KEY]
    )


__all__ = [
    "DEFAULT_CODE_KEY",
    "FEES_CODE_KEY",
    "LEGACY_CODES",
    "TaxCodes",
    "load_tax_codes",
    "normalize_code",
    "save_tax_codes",
]
