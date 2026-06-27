from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.features.payment.providers.base import (
    ApiPaymentProvider,
    CaptureResult,
    InitiationRequest,
    InitiationResult,
    WebhookResult,
)
from app.features.payment.utils.payzen import (
    capture_payzen_transaction,
    create_payzen_form_token,
    validate_ipn_signature,
)


class PayzenProvider(ApiPaymentProvider):
    """Represents payzen provider."""

    code = "payzen"

    async def initiate_payment(self, request: InitiationRequest) -> InitiationResult:
        """Execute initiate payment."""
        payzen_result = await create_payzen_form_token(
            amount=request.amount,
            currency=request.currency,
            order_id=request.order_id,
            customer_email=request.customer_email,
            customer_reference=request.customer_reference,
            customer_first_name=request.customer_first_name,
            customer_last_name=request.customer_last_name,
            return_url=request.return_url,
            form_action=request.form_action,
            metadata=request.metadata,
            manual_validation=settings.PAYZEN_MANUAL_VALIDATION,
        )

        return InitiationResult(
            provider_code=self.code,
            provider_reference=request.order_id,
            form_token=payzen_result["form_token"],
            server_url=payzen_result["server_url"],
            public_key=payzen_result["public_key"],
            raw_response=payzen_result.get("raw_response"),
        )

    def parse_webhook_notification(self, payload: dict[str, Any]) -> WebhookResult:
        """Parse webhook notification."""
        fields = validate_ipn_signature(payload)

        provider_reference: str | None = None
        order_id = fields.get("order_id")
        if order_id is not None:
            normalized_order_id = str(order_id).strip()
            provider_reference = normalized_order_id or None

        # Fallback kept for robustness if an upstream payload misses order_id.
        if provider_reference is None:
            trans_id = fields.get("trans_uuid") or fields.get("trans_id")
            if trans_id is not None:
                normalized_trans_id = str(trans_id).strip()
                provider_reference = normalized_trans_id or None

        payment_status = fields.get("trans_status")
        if not isinstance(payment_status, str):
            payment_status = None

        return WebhookResult(
            provider_code=self.code,
            provider_reference=provider_reference,
            payment_status=payment_status,
            payload=fields,
        )

    async def capture(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> CaptureResult:
        """Capture (validate) an authorised PayZen transaction — triggers the debit.

        ``payment_reference`` is the PayZen transaction UUID recorded from the IPN.
        Raises AppError (from the util) if the gateway rejects the capture.
        """
        await capture_payzen_transaction(payment_reference)
        return CaptureResult(
            status="completed",
            provider_reference=payment_reference,
            message="Capture PayZen effectuée.",
        )
