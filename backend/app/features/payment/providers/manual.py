from __future__ import annotations

from app.features.payment.providers.base import (
    InitiationRequest,
    InitiationResult,
    ManualPaymentProvider,
    ValidationResult,
)

MANUAL_STATUS_AWAITING_VALIDATION = "AwaitingValidation"
MANUAL_STATUS_COMPLETED = "Completed"
MANUAL_STATUS_FAILED = "Failed"


class _ManualProviderBase(ManualPaymentProvider):
    """Represents manual provider base."""

    instructions: str = ""

    async def register_intent(self, request: InitiationRequest) -> InitiationResult:
        """Execute register intent."""
        return InitiationResult(
            provider_code=self.code,
            provider_reference=request.order_id,
            instructions=self.instructions,
        )

    async def confirm_received(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reference: str | None = None,
    ) -> ValidationResult:
        """Execute confirm received."""
        metadata: dict[str, object] = {"admin_user_id": admin_user_id}
        if reference is not None:
            metadata["reference"] = reference

        return ValidationResult(
            provider_code=self.code,
            payment_status=MANUAL_STATUS_COMPLETED,
            provider_reference=reference or payment_reference,
            metadata=metadata,
        )

    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult:
        """Execute reject."""
        return ValidationResult(
            provider_code=self.code,
            payment_status=MANUAL_STATUS_FAILED,
            provider_reference=payment_reference,
            metadata={
                "admin_user_id": admin_user_id,
                "reason": reason,
            },
        )


class ManualCheckProvider(_ManualProviderBase):
    """Represents manual check provider."""

    code = "manual_check"
    instructions = (
        "Veuillez libeller votre chèque à l'ordre du marchand et l'envoyer "
        "à l'adresse postale indiquée. Votre commande sera validée à réception "
        "et après encaissement du chèque."
    )


class ManualTransferProvider(_ManualProviderBase):
    """Represents manual transfer provider."""

    code = "manual_transfer"
    instructions = (
        "Veuillez effectuer un virement bancaire vers le compte indiqué en "
        "mentionnant la référence de paiement. Votre commande sera validée "
        "dès réception du virement."
    )
