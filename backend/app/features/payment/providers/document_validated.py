from __future__ import annotations

from app.features.payment.providers.base import (
    AttachmentResult,
    DocumentValidatedProvider,
    InitiationRequest,
    InitiationResult,
    ValidationResult,
)

DOCUMENT_STATUS_DOCUMENT_REQUIRED = "DocumentRequired"
DOCUMENT_STATUS_DOCUMENT_UPLOADED = "DocumentUploaded"
DOCUMENT_STATUS_UNDER_REVIEW = "UnderReview"
DOCUMENT_STATUS_APPROVED = "Completed"
DOCUMENT_STATUS_REJECTED = "Failed"


class PublicPurchaseOrderProvider(DocumentValidatedProvider):
    """Represents public purchase order provider."""

    code = "po_public"
    instructions = (
        "Veuillez téléverser votre bon de commande signé (PDF, JPG ou PNG) "
        "afin que notre équipe puisse valider votre demande. "
        "Votre commande sera confirmée après vérification du document."
    )

    async def register_intent(self, request: InitiationRequest) -> InitiationResult:
        """Execute register intent."""
        return InitiationResult(
            provider_code=self.code,
            provider_reference=request.order_id,
            instructions=self.instructions,
        )

    async def attach_document(
        self,
        *,
        payment_reference: str,
        file_key: str,
        filename: str,
    ) -> AttachmentResult:
        """Execute attach document."""
        return AttachmentResult(
            file_key=file_key,
            filename=filename,
            metadata={"payment_reference": payment_reference},
        )

    async def approve(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        comment: str | None = None,
    ) -> ValidationResult:
        """Execute approve."""
        return ValidationResult(
            provider_code=self.code,
            payment_status=DOCUMENT_STATUS_APPROVED,
            provider_reference=payment_reference,
            metadata={
                "admin_user_id": admin_user_id,
                "comment": comment,
            },
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
            payment_status=DOCUMENT_STATUS_REJECTED,
            provider_reference=payment_reference,
            metadata={
                "admin_user_id": admin_user_id,
                "reason": reason,
            },
        )
