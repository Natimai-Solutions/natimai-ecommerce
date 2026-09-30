"""Payment method types, and the methods the shop builds on them.

A *type* is a provider class in the code (card, PayPal, cash, cheque,
transfer, purchase order): its behaviour is fixed. A *method* is a row of
``payment_methods`` the admin creates on a type, names, prices, caps, orders
and switches on or off — several methods can share a type (« Virement BNP »
and « Virement Banque de Tahiti »), each with its own instructions.

The instructions sent to the customer come, in this order, from the method,
from its type (Paramètres système, ``payment_instructions_<code>``), then from
the provider's default text.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.models.payment_method import PaymentMethod
from app.features.payment.providers import SUPPORTED_PROVIDERS
from app.features.payment.providers.base import (
    ApiPaymentProvider,
    DocumentValidatedProvider,
    ManualPaymentProvider,
)
from app.features.system.payment_instructions import load_payment_instructions

FAMILY_CARD = "card"
FAMILY_WALLET = "wallet"
FAMILY_MANUAL = "manual"
FAMILY_DOCUMENT = "document"

_LABELS: dict[str, str] = {
    "payzen": "Carte bancaire (PayZen)",
    "paypal": "PayPal",
    "manual_cash": "Espèces",
    "manual_check": "Chèque",
    "manual_transfer": "Virement bancaire",
    "po_public": "Bon de commande",
}
_API_FAMILIES: dict[str, str] = {"paypal": FAMILY_WALLET}


@dataclass(frozen=True)
class PaymentMethodType:
    code: str
    label: str
    family: str
    #: The payment waits for an admin (manual and document types).
    requires_admin_validation: bool
    requires_document_upload: bool
    #: The customer receives instructions (manual and document types).
    supports_instructions: bool
    default_instructions: str | None


def _family(code: str, provider_class: type) -> str:
    if issubclass(provider_class, DocumentValidatedProvider):
        return FAMILY_DOCUMENT
    if issubclass(provider_class, ManualPaymentProvider):
        return FAMILY_MANUAL
    if issubclass(provider_class, ApiPaymentProvider):
        return _API_FAMILIES.get(code, FAMILY_CARD)
    return FAMILY_MANUAL


def method_types() -> list[PaymentMethodType]:
    """Every type implemented in the code, in a stable order."""
    types = []
    for code, provider_class in SUPPORTED_PROVIDERS.items():
        family = _family(code, provider_class)
        offline = family in (FAMILY_MANUAL, FAMILY_DOCUMENT)
        default = getattr(provider_class, "instructions", None)
        types.append(
            PaymentMethodType(
                code=code,
                label=_LABELS.get(code, code),
                family=family,
                requires_admin_validation=offline,
                requires_document_upload=family == FAMILY_DOCUMENT,
                supports_instructions=offline,
                default_instructions=default.strip()
                if isinstance(default, str) and default.strip()
                else None,
            )
        )
    return types


def method_type(code: str) -> PaymentMethodType | None:
    normalized = code.strip().lower()
    return next((t for t in method_types() if t.code == normalized), None)


def type_label(code: str) -> str:
    return _LABELS.get(code, code)


def clean_text(value: str | None) -> str | None:
    """Trimmed text, None when empty."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


async def shop_instructions(
    session: AsyncSession, *, method: PaymentMethod | None, provider_code: str
) -> str | None:
    """The shop's instructions for a payment on ``method``: the method's own,
    else its type's (Paramètres système). None keeps the provider's default."""
    if method is not None:
        own = clean_text(method.instructions)
        if own:
            return own
    return await load_payment_instructions(session, provider_code)


__all__ = [
    "FAMILY_CARD",
    "FAMILY_DOCUMENT",
    "FAMILY_MANUAL",
    "FAMILY_WALLET",
    "PaymentMethodType",
    "clean_text",
    "method_type",
    "method_types",
    "shop_instructions",
    "type_label",
]
