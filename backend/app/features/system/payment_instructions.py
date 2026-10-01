"""Payment instructions shown and e-mailed to the customer, editable in base.

Each manual method (cash, cheque, transfer) comes with a default text in its
provider class. The shop replaces it from the back-office (Paramètres) with its
own: office address and opening hours for cash, payee name and postal address
for cheques, IBAN / BIC / account holder for transfers. An empty setting keeps
the default text.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass(frozen=True)
class PaymentInstructionSpec:
    provider_code: str
    description: str

    @property
    def key(self) -> str:
        return f"payment_instructions_{self.provider_code}"


PAYMENT_INSTRUCTION_SETTINGS: tuple[PaymentInstructionSpec, ...] = (
    PaymentInstructionSpec(
        "manual_cash",
        "Instructions du paiement en espèces (adresse du bureau, horaires). "
        "Vide = texte par défaut",
    ),
    PaymentInstructionSpec(
        "manual_check",
        "Instructions du paiement par chèque (ordre, adresse d'envoi). "
        "Vide = texte par défaut",
    ),
    PaymentInstructionSpec(
        "manual_transfer",
        "Instructions du virement (titulaire, IBAN, BIC, référence à indiquer). "
        "Vide = texte par défaut",
    ),
)


def instruction_key(provider_code: str) -> str:
    return f"payment_instructions_{provider_code}"


async def load_payment_instructions(
    session: AsyncSession, provider_code: str
) -> str | None:
    """The shop's own instructions for ``provider_code``, or None (default)."""
    from app.core import runtime_settings

    key = instruction_key(provider_code)
    if runtime_settings.spec_for(key) is None:
        return None
    value = str(await runtime_settings.get(key, session) or "").strip()
    return value or None
