from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class PaymentProviderError(Exception):
    """Base exception for provider layer errors."""


class UnknownPaymentProviderError(PaymentProviderError):
    """Raised when the provider registry receives an unknown provider code."""

    def __init__(self, provider_code: str) -> None:
        self.provider_code = provider_code
        super().__init__(f"Unknown payment provider: {provider_code}")


@dataclass(slots=True)
class InitiationRequest:
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
    provider_code: str
    provider_reference: str | None
    payment_status: str | None
    payload: dict[str, Any]


@dataclass(slots=True)
class ValidationResult:
    provider_code: str
    payment_status: str
    provider_reference: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class AttachmentResult:
    file_key: str
    filename: str
    mimetype: str | None = None
    size: int | None = None
    metadata: dict[str, Any] | None = None


class PaymentProvider(ABC):
    code: str


class ApiPaymentProvider(PaymentProvider, ABC):
    @abstractmethod
    async def initiate_payment(
        self, request: InitiationRequest
    ) -> InitiationResult: ...

    @abstractmethod
    def parse_webhook_notification(self, payload: dict[str, Any]) -> WebhookResult: ...


class ManualPaymentProvider(PaymentProvider, ABC):
    @abstractmethod
    async def register_intent(self, request: InitiationRequest) -> InitiationResult: ...

    @abstractmethod
    async def confirm_received(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reference: str | None = None,
    ) -> ValidationResult: ...

    @abstractmethod
    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult: ...


class DocumentValidatedProvider(PaymentProvider, ABC):
    @abstractmethod
    async def register_intent(self, request: InitiationRequest) -> InitiationResult: ...

    @abstractmethod
    async def attach_document(
        self,
        *,
        payment_reference: str,
        file_key: str,
        filename: str,
    ) -> AttachmentResult: ...

    @abstractmethod
    async def approve(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        comment: str | None = None,
    ) -> ValidationResult: ...

    @abstractmethod
    async def reject(
        self,
        *,
        payment_reference: str,
        admin_user_id: str,
        reason: str,
    ) -> ValidationResult: ...
