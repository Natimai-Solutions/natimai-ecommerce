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
    ManualCheckProvider,
    ManualTransferProvider,
)
from app.features.payment.providers.payzen import PayzenProvider

SUPPORTED_PROVIDERS: dict[str, type[PaymentProvider]] = {
    PayzenProvider.code: PayzenProvider,
    ManualCheckProvider.code: ManualCheckProvider,
    ManualTransferProvider.code: ManualTransferProvider,
    PublicPurchaseOrderProvider.code: PublicPurchaseOrderProvider,
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
]
