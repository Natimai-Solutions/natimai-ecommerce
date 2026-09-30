from app.features.payment.providers.base import (
    ApiPaymentProvider,
    AttachmentResult,
    DocumentValidatedProvider,
    InitiationRequest,
    InitiationResult,
    ManualPaymentProvider,
    PaymentProvider,
    PaymentProviderError,
    UnknownPaymentProviderError,
    ValidationResult,
    WebhookResult,
)
from app.features.payment.providers.document_validated import (
    PublicPurchaseOrderProvider,
)
from app.features.payment.providers.manual import (
    ManualCashProvider,
    ManualCheckProvider,
    ManualTransferProvider,
)
from app.features.payment.providers.payzen import PayzenProvider

SUPPORTED_PROVIDERS: dict[str, type[PaymentProvider]] = {
    PayzenProvider.code: PayzenProvider,
    ManualCashProvider.code: ManualCashProvider,
    ManualCheckProvider.code: ManualCheckProvider,
    ManualTransferProvider.code: ManualTransferProvider,
    PublicPurchaseOrderProvider.code: PublicPurchaseOrderProvider,
}


def get_provider(provider_code: str) -> PaymentProvider:
    """Get provider."""
    normalized_code = provider_code.strip().lower()
    provider_class = SUPPORTED_PROVIDERS.get(normalized_code)
    if provider_class is None:
        raise UnknownPaymentProviderError(normalized_code)

    return provider_class()


def provider_supports_in_app_refund(provider_code: str | None) -> bool:
    """Whether the admin UI can initiate a refund for this provider (else hidden).

    Unknown / missing codes default to ``False``.
    """
    if not provider_code:
        return False
    provider_class = SUPPORTED_PROVIDERS.get(provider_code.strip().lower())
    return bool(provider_class and provider_class.supports_in_app_refund)


__all__ = [
    "ApiPaymentProvider",
    "AttachmentResult",
    "DocumentValidatedProvider",
    "InitiationRequest",
    "InitiationResult",
    "ManualCashProvider",
    "ManualCheckProvider",
    "ManualPaymentProvider",
    "ManualTransferProvider",
    "PaymentProvider",
    "PaymentProviderError",
    "PayzenProvider",
    "PublicPurchaseOrderProvider",
    "SUPPORTED_PROVIDERS",
    "UnknownPaymentProviderError",
    "ValidationResult",
    "WebhookResult",
    "get_provider",
    "provider_supports_in_app_refund",
]
