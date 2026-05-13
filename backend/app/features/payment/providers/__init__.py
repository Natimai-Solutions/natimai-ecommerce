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
from app.features.payment.providers.payzen import PayzenProvider

SUPPORTED_PROVIDERS: dict[str, type[PaymentProvider]] = {
    PayzenProvider.code: PayzenProvider,
}


def get_provider(provider_code: str) -> PaymentProvider:
    normalized_code = provider_code.strip().lower()
    provider_class = SUPPORTED_PROVIDERS.get(normalized_code)
    if provider_class is None:
        raise UnknownPaymentProviderError(normalized_code)

    return provider_class()


__all__ = [
    "ApiPaymentProvider",
    "AttachmentResult",
    "DocumentValidatedProvider",
    "InitiationRequest",
    "InitiationResult",
    "ManualPaymentProvider",
    "PaymentProvider",
    "PaymentProviderError",
    "PayzenProvider",
    "SUPPORTED_PROVIDERS",
    "UnknownPaymentProviderError",
    "ValidationResult",
    "WebhookResult",
    "get_provider",
]
