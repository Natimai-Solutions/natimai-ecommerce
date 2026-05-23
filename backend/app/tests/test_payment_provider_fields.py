from decimal import Decimal
from uuid import uuid4

from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_method import PaymentMethod


def test_payment_provider_defaults() -> None:
    payment = Payment(
        amount=Decimal("100.00"),
        currency="XPF",
        user_id=uuid4(),
    )

    assert payment.provider_code == "payzen"
    assert payment.provider_reference is None
    assert payment.provider_data is None


def test_payment_method_provider_defaults() -> None:
    method = PaymentMethod(
        name="Carte bancaire",
        fee=Decimal("0.00"),
    )

    assert method.provider_code == "payzen"
    assert method.requires_admin_validation is False
    assert method.requires_document_upload is False
    assert method.sort_order == 0
