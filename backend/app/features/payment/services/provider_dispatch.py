from __future__ import annotations

import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment_method import crud_payment_method
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import (
    ApiPaymentProvider,
    InitiationRequest,
    InitiationResult,
    ManualPaymentProvider,
    WebhookResult,
)


class PaymentApiProviderResolutionError(RuntimeError):
    """Raised when a provider does not support API initiation/webhooks."""


class PaymentManualProviderResolutionError(RuntimeError):
    """Raised when a provider does not support the manual validation workflow."""


class PaymentMethodResolutionError(RuntimeError):
    """Raised when payment method cannot resolve to a valid provider."""


class PaymentMethodNotFoundError(PaymentMethodResolutionError):
    """Raised when a payment method does not exist."""


class PaymentMethodInactiveError(PaymentMethodResolutionError):
    """Raised when a payment method is disabled."""


def resolve_api_provider(provider_code: str) -> ApiPaymentProvider:
    """Resolve and validate an API-capable payment provider."""
    provider = get_provider(provider_code)
    if not isinstance(provider, ApiPaymentProvider):
        raise PaymentApiProviderResolutionError(
            f"Payment provider '{provider_code}' does not support API initiation"
        )

    return provider


async def resolve_provider_code_for_payment_method(
    session: AsyncSession,
    payment_method_id: uuid.UUID,
) -> str:
    """Resolve the provider code for an active payment method."""
    try:
        payment_method = await crud_payment_method.read(session, id=payment_method_id)
    except RecordNotFoundError as e:
        raise PaymentMethodNotFoundError(
            f"Payment method '{payment_method_id}' not found"
        ) from e

    if not payment_method.is_active or not payment_method.is_admin_active:
        raise PaymentMethodInactiveError(
            f"Payment method '{payment_method_id}' is disabled"
        )

    provider_code = payment_method.provider_code.strip().lower()
    if not provider_code:
        raise PaymentMethodResolutionError(
            f"Payment method '{payment_method_id}' has no provider code"
        )

    return provider_code


async def initiate_api_payment(
    provider_code: str,
    request: InitiationRequest,
) -> InitiationResult:
    """Initiate a payment through an API provider."""
    provider = resolve_api_provider(provider_code)
    return await provider.initiate_payment(request)


def parse_api_webhook(
    provider_code: str,
    payload: dict[str, Any],
) -> WebhookResult:
    """Parse a webhook payload using the provider parser."""
    provider = resolve_api_provider(provider_code)
    return provider.parse_webhook_notification(payload)


def resolve_manual_provider(provider_code: str) -> ManualPaymentProvider:
    """Resolve and validate a manual payment provider."""
    provider = get_provider(provider_code)
    if not isinstance(provider, ManualPaymentProvider):
        raise PaymentManualProviderResolutionError(
            f"Payment provider '{provider_code}' is not a manual provider"
        )

    return provider


async def register_manual_payment_intent(
    provider_code: str,
    request: InitiationRequest,
) -> InitiationResult:
    """Register a payment intent with a manual provider."""
    provider = resolve_manual_provider(provider_code)
    return await provider.register_intent(request)
