from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class PaymentProvider(ABC):
    """Represents payment provider."""

    code: str


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
