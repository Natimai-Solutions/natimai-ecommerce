from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
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


#: Outcomes a provider notification can report, whatever the provider
#: (PayZen « PAID », PayPal « PAYMENT.CAPTURE.COMPLETED »…).
OUTCOME_COMPLETED = "completed"
OUTCOME_AUTHORIZED = "authorized"
OUTCOME_FAILED = "failed"
OUTCOME_REFUNDED = "refunded"
PROVIDER_OUTCOMES: tuple[str, ...] = (
    OUTCOME_COMPLETED,
    OUTCOME_AUTHORIZED,
    OUTCOME_FAILED,
    OUTCOME_REFUNDED,
)


@dataclass(slots=True)
class ProviderOutcome:
    """A provider notification (webhook) or confirmation, normalized.

    ``status`` is one of :data:`PROVIDER_OUTCOMES`, or None for an event that
    does not change the payment (order created, approval pending…).
    ``payment_reference`` finds our payment: its id, or the provider reference
    stored at initiation. ``amount_minor`` / ``currency`` are what the provider
    charged, checked against what was asked. ``event_id`` deduplicates
    deliveries; ``extra`` goes into ``provider_data`` (capture id…).
    """

    provider_code: str
    status: str | None
    payment_reference: str | None = None
    event_id: str | None = None
    event_type: str | None = None
    transaction_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


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
class CaptureResult:
    """Outcome of capturing a previously authorised payment (deferred CB debit)."""

    status: str  # "completed" | "failed"
    provider_reference: str | None = None
    message: str | None = None
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

    # Whether a refund can be *initiated from the admin UI* for this provider.
    # Only card providers (PayZen) move money back through the app; manual /
    # document refunds happen out-of-band, so their button is hidden. Flip this
    # to True on a future provider to surface the refund button automatically.
    supports_in_app_refund: bool = False

    def capture_reference(self, provider_data: Mapping[str, Any] | None) -> str | None:
        """The provider's reference of an authorised payment to capture.

        Default: the PayZen transaction uuid recorded from the notification.
        """
        data = provider_data or {}
        raw = data.get("trans_uuid") or data.get("trans_id")
        return str(raw) if raw else None

    def refund_reference(
        self,
        *,
        provider_data: Mapping[str, Any] | None,
        provider_reference: str | None,
        fallback: str,
    ) -> str:
        """The provider's reference of a captured payment to refund."""
        return provider_reference or fallback

    async def capture(
        self,
        *,
        payment_reference: str,
        amount: Decimal,
        currency: str,
    ) -> CaptureResult:
        """Capture a previously authorised payment (deferred CB debit).

        Default: unsupported — only card providers that authorise at checkout
        (PayZen in manual-validation mode) implement this.
        """
        raise PaymentProviderError(
            f"Provider '{self.code}' does not support deferred capture"
        )

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

    #: Notifications handled by the generic pipeline (POST /payments/webhooks/
    #: {code}); PayZen keeps its historical IPN route.
    generic_webhooks: bool = False

    async def parse_webhook(
        self, raw_body: bytes, headers: Mapping[str, str]
    ) -> ProviderOutcome:
        """Authenticate a raw notification (signature) and normalize it.

        Raises :class:`PaymentProviderError` when the notification cannot be
        trusted.
        """
        raise PaymentProviderError(
            f"Provider '{self.code}' has no generic webhook support"
        )

    async def confirm_payment(
        self, *, provider_reference: str, provider_data: Mapping[str, Any] | None
    ) -> ProviderOutcome:
        """Server-side step after the customer approved the payment on the
        provider's page (PayPal: capture or authorize the order)."""
        raise PaymentProviderError(f"Provider '{self.code}' has no confirmation step")


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
