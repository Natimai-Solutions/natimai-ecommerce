from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


class PaymentProviderError(Exception):
    """Base exception for provider layer errors."""


class UnknownPaymentProviderError(PaymentProviderError):
    """Raised when the provider registry receives an unknown provider code."""

    def __init__(self, provider_code: str) -> None:
        """Initialize the unknown payment provider error instance."""
        self.provider_code = provider_code
        super().__init__(f"Unknown payment provider: {provider_code}")


@dataclass(slots=True)
class InitiationRequest:
    """Represents initiation request."""

    amount: int
    currency: str
    order_id: str
    customer_email: str
    customer_reference: str
    customer_first_name: str = ""
    customer_last_name: str = ""
    return_url: str | None = None
    form_action: str = "SILENT"
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class InitiationResult:
    """Represents initiation result."""

    provider_code: str
    provider_reference: str | None = None
    redirect_url: str | None = None
    form_token: str | None = None
    server_url: str | None = None
    public_key: str | None = None
    instructions: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class WebhookResult:
    """Represents webhook result."""

    provider_code: str
    provider_reference: str | None
    payment_status: str | None
    payload: dict[str, Any]


@dataclass(slots=True)
class ValidationResult:
    """Represents validation result."""

    provider_code: str
    payment_status: str
    provider_reference: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class AttachmentResult:
    """Represents attachment result."""

    file_key: str
    filename: str
    mimetype: str | None = None
    size: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class RefundResult:
    """Outcome of a provider refund attempt.

    ``status`` is one of ``completed`` (money returned / decision applied) or
    ``pending`` (recorded, awaiting an out-of-band action — e.g. a card refund to
    finalise in the provider back-office). ``failed`` is reserved for API errors.
    """

    status: str
    provider_reference: str | None = None
    message: str | None = None
    metadata: dict[str, Any] | None = None


class PaymentProvider(ABC):
    """Represents payment provider."""

    code: str

    async def refund(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        """Refund (full or partial) of a captured payment.

        Default contract: no automated refund API — the refund is *recorded* and
        must be finalised out-of-band (e.g. a PayZen card refund in the back
        office). Manual/document providers override this with an immediate
        ``completed`` decision.
        """
        return RefundResult(
            status="pending",
            message=(
                "Remboursement enregistré — à finaliser auprès du prestataire "
                "(back-office PayZen)."
            ),
        )


class ApiPaymentProvider(PaymentProvider, ABC):
    """Define the API-driven payment provider contract."""

    @abstractmethod
    async def initiate_payment(self, request: InitiationRequest) -> InitiationResult:
        """Initiate a payment with the external provider."""
        ...

    @abstractmethod
    def parse_webhook_notification(self, payload: dict[str, Any]) -> WebhookResult:
        """Parse a provider webhook payload into a normalized result."""
        ...


class ManualPaymentProvider(PaymentProvider, ABC):
    """Define the manual-payment provider contract."""

    @abstractmethod
    async def register_intent(self, request: InitiationRequest) -> InitiationResult:
        """Register a manual payment intent."""
        ...

    @abstractmethod
    async def confirm_received(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reference: str | None = None,
    ) -> ValidationResult:
        """Confirm that the manual payment has been received."""
        ...

    @abstractmethod
    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult:
        """Reject a manual payment intent."""
        ...

    async def refund(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        """Manual refund: an immediate decision — the accounting entry / cheque
        reissue / transfer is performed off-system by the back office."""
        return RefundResult(
            status="completed",
            message="Remboursement manuel enregistré (écriture comptable à effectuer).",
        )


class DocumentValidatedProvider(PaymentProvider, ABC):
    """Define the document-validated payment provider contract."""

    @abstractmethod
    async def register_intent(self, request: InitiationRequest) -> InitiationResult:
        """Register a document-validated payment intent."""
        ...

    @abstractmethod
    async def attach_document(
        self,
        *,
        payment_reference: str,
        file_key: str,
        filename: str,
    ) -> AttachmentResult:
        """Attach a supporting document to a payment reference."""
        ...

    @abstractmethod
    async def approve(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        comment: str | None = None,
    ) -> ValidationResult:
        """Approve a document-validated payment."""
        ...

    @abstractmethod
    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult:
        """Reject a document-validated payment."""
        ...

    async def refund(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
        reason: str | None = None,
    ) -> RefundResult:
        """Document-validated refund (e.g. purchase order): a pure admin
        decision, applied immediately."""
        return RefundResult(
            status="completed",
            message="Remboursement validé (décision administrative).",
        )
