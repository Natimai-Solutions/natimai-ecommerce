"""Admin switches of the payment service providers (R3-P5)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.payment.services.provider_settings import (
    PSP_DEFAULTS,
    provider_states,
    set_provider_enabled,
)

router = APIRouter(prefix="/admin/payment-providers", tags=["admin-payment"])


class PaymentProviderPublic(BaseModel):
    code: str
    label: str
    enabled: bool
    credentials_present: bool
    implemented: bool
    #: Switched on, implemented and with credentials: takes new payments.
    available: bool


class PaymentProviderUpdate(BaseModel):
    enabled: bool


async def _list(session: SessionDep) -> list[PaymentProviderPublic]:
    return [
        PaymentProviderPublic(
            code=state.code,
            label=state.label,
            enabled=state.enabled,
            credentials_present=state.credentials_present,
            implemented=state.implemented,
            available=state.available,
        )
        # fresh : l'écran relit ce qu'il vient d'enregistrer, même si le GET du
        # rechargement tombe sur un autre worker que le PUT (instantané des
        # réglages par processus, cf. app.core.runtime_settings).
        for state in await provider_states(session, fresh=True)
    ]


@router.get("", response_model=list[PaymentProviderPublic])
async def list_payment_providers(
    session: SessionDep, _admin: CurrentSuperUser
) -> list[PaymentProviderPublic]:
    """PayZen, PayPal and Stripe: switch, credentials, availability."""
    return await _list(session)


@router.put("/{provider_code}", response_model=list[PaymentProviderPublic])
async def update_payment_provider(
    provider_code: str,
    body: PaymentProviderUpdate,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> list[PaymentProviderPublic]:
    """Switch a provider on or off; its payment methods follow at once."""
    code = provider_code.strip().lower()
    if code not in PSP_DEFAULTS:
        raise AppError(
            code="payment.provider.unknown",
            status_code=404,
            message=f"Prestataire inconnu : {provider_code}",
            details={"allowed": list(PSP_DEFAULTS)},
        )
    await set_provider_enabled(session, code, body.enabled)
    await session.commit()
    return await _list(session)
