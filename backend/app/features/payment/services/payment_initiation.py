"""Shared payment-initiation flow.

Used by both ``POST /payments/initiate`` and the cart checkout
(``POST /cart/checkout``). Resolves the provider for a payment method, creates
the payment, dispatches to the provider (API SmartForm / manual / document) and
returns the provider result.

Does **not** commit — the caller owns the transaction (the checkout creates the
order + payment atomically in a single transaction).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.crud.payment import crud_payment
from app.features.payment.models.payment import Payment, PaymentCreate
from app.features.payment.providers import get_provider
from app.features.payment.providers.base import (
    ApiPaymentProvider,
    DocumentValidatedProvider,
    InitiationRequest,
    ManualPaymentProvider,
    UnknownPaymentProviderError,
)
from app.features.payment.services.document_payment import (
    register_intent as register_document_intent,
)
from app.features.payment.services.eligibility import check_payment_method_eligible
from app.features.payment.services.manual_payment import (
    register_intent as register_manual_intent,
)
from app.features.payment.services.provider_dispatch import (
    PaymentMethodInactiveError,
    PaymentMethodNotFoundError,
    PaymentMethodResolutionError,
    initiate_api_payment,
    resolve_provider_code_for_payment_method,
)
from app.utils.money import decimal_to_minor_units


@dataclass
class PaymentInitiationResult:
    """Outcome of a payment initiation (payment is added to the session, not committed)."""

    payment: Payment
    provider_code: str
    provider_reference: str | None
    form_token: str | None = None
    server_url: str | None = None
    public_key: str | None = None
    redirect_url: str | None = None
    instructions: str | None = None


def _build_initiation_request(
    *,
    payment_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    return_url: str | None,
    metadata: dict[str, Any] | None,
    current_user: Any,
) -> InitiationRequest:
    amount_minor = decimal_to_minor_units(amount, currency)
    name_parts = current_user.full_name.split() if current_user.full_name else []
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    return InitiationRequest(
        amount=amount_minor,
        currency=currency,
        order_id=str(payment_id),
        customer_email=current_user.email,
        customer_reference=str(current_user.id),
        customer_first_name=first_name,
        customer_last_name=last_name,
        return_url=return_url,
        form_action="SILENT",
        metadata=metadata,
    )


async def initiate_payment_for_method(
    session: AsyncSession,
    *,
    payment_method_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    order_id: uuid.UUID | None,
    return_url: str | None,
    metadata: dict[str, Any] | None,
    current_user: Any,
    kind: str = "full",
) -> PaymentInitiationResult:
    """Create a payment for ``payment_method_id`` and run the provider initiation.

    ``kind`` says which part of the order the payment settles (full, deposit
    or balance). Raises ``AppError`` for unknown/inactive/ineligible methods
    or providers. The returned payment is added to the session but **not**
    committed.
    """
    # 1. Resolve provider (precise errors before the eligibility guard).
    try:
        provider_code = await resolve_provider_code_for_payment_method(
            session, payment_method_id
        )
    except PaymentMethodNotFoundError as e:
        raise AppError(
            code="payment.method.not_found",
            status_code=404,
            message=str(e),
            details={"payment_method_id": str(payment_method_id)},
        ) from e
    except PaymentMethodInactiveError as e:
        raise AppError(
            code="payment.method.inactive",
            status_code=400,
            message=str(e),
            details={"payment_method_id": str(payment_method_id)},
        ) from e
    except PaymentMethodResolutionError as e:
        raise AppError(
            code="payment.method.resolution_failed",
            status_code=400,
            message=str(e),
            details={"payment_method_id": str(payment_method_id)},
        ) from e

    # 2. Group eligibility + max_amount check.
    eligible = await check_payment_method_eligible(
        session,
        payment_method_id=payment_method_id,
        price_group_id=current_user.price_group_id,
        amount=amount,
    )
    if not eligible:
        raise AppError(
            code="payment.method.not_eligible",
            status_code=403,
            message="This payment method is not available for your account or order amount",
            details={"payment_method_id": str(payment_method_id)},
        )

    # 3. Provider implementation.
    try:
        provider = get_provider(provider_code)
    except UnknownPaymentProviderError as e:
        raise AppError(
            code="payment.provider.unknown",
            status_code=400,
            message=str(e),
            details={"provider_code": provider_code},
        ) from e

    # 4. Persist the payment (pending) — caller commits.
    payment = await crud_payment.create_payment_with_log(
        session,
        payment_data=PaymentCreate(
            amount=amount,
            currency=currency,
            provider_code=provider_code,
            order_id=order_id,
            user_id=current_user.id,
        ),
        user=current_user,
        commit=False,
    )
    payment.payment_method_id = payment_method_id
    payment.kind = kind

    initiation_request = _build_initiation_request(
        payment_id=payment.id,
        amount=amount,
        currency=currency,
        return_url=return_url,
        metadata=metadata,
        current_user=current_user,
    )

    # 5. Dispatch by provider type.
    if isinstance(provider, ApiPaymentProvider):
        provider_result = await initiate_api_payment(provider_code, initiation_request)

        payment.provider_code = provider_code
        payment.provider_reference = provider_result.provider_reference or str(
            payment.id
        )
        provider_data: dict[str, object] = {}
        if isinstance(provider_result.raw_response, dict):
            provider_data.update(provider_result.raw_response)
        if provider_code == "payzen":
            provider_data["form_token"] = provider_result.form_token
            provider_data["server_url"] = provider_result.server_url
            provider_data["public_key"] = provider_result.public_key
            provider_data["order_id"] = str(payment.id)
        payment.provider_data = provider_data or None
        session.add(payment)

    elif isinstance(provider, ManualPaymentProvider):
        provider_result = await provider.register_intent(initiation_request)

        payment.provider_code = provider_code
        payment.provider_reference = provider_result.provider_reference or str(
            payment.id
        )
        payment.provider_data = provider_result.raw_response
        await register_manual_intent(
            session,
            payment=payment,
            instructions=provider_result.instructions,
            user=current_user,
        )

    elif isinstance(provider, DocumentValidatedProvider):
        provider_result = await provider.register_intent(initiation_request)

        payment.provider_code = provider_code
        payment.provider_reference = provider_result.provider_reference or str(
            payment.id
        )
        payment.provider_data = provider_result.raw_response
        await register_document_intent(
            session,
            payment=payment,
            instructions=provider_result.instructions,
            user=current_user,
        )

    else:
        raise AppError(
            code="payment.provider.unsupported_for_initiation",
            status_code=400,
            message=f"Provider '{provider_code}' does not support payment initiation",
            details={"provider_code": provider_code},
        )

    return PaymentInitiationResult(
        payment=payment,
        provider_code=provider_code,
        provider_reference=payment.provider_reference,
        form_token=provider_result.form_token,
        server_url=provider_result.server_url,
        public_key=provider_result.public_key,
        redirect_url=provider_result.redirect_url,
        instructions=provider_result.instructions,
    )
