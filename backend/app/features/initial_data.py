from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.features.payment.crud.payment_method import crud_payment_method
from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment_method import (
    PaymentMethod,
    PaymentMethodCreate,
)
from app.features.payment.models.payment_status import PaymentStatusCreate
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_DOCUMENT_REQUIRED,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_UNDER_REVIEW,
)
from app.features.payment.providers.manual import (
    MANUAL_STATUS_AWAITING_VALIDATION,
    MANUAL_STATUS_COMPLETED,
    MANUAL_STATUS_FAILED,
)

DEFAULT_PAYMENT_STATUSES: tuple[tuple[str, str], ...] = (
    ("Pending", "Payment initiated, awaiting provider action"),
    (MANUAL_STATUS_AWAITING_VALIDATION, "Awaiting manual admin validation"),
    (DOCUMENT_STATUS_DOCUMENT_REQUIRED, "Waiting for document upload from client"),
    (DOCUMENT_STATUS_DOCUMENT_UPLOADED, "Document uploaded, awaiting AV scan"),
    (DOCUMENT_STATUS_UNDER_REVIEW, "Document under admin review"),
    (MANUAL_STATUS_COMPLETED, "Payment confirmed and captured"),
    (MANUAL_STATUS_FAILED, "Payment failed or was rejected"),
)


async def _seed_payment_statuses(session: AsyncSession) -> None:
    for name, description in DEFAULT_PAYMENT_STATUSES:
        existing = await crud_payment_status.get_by_name(session, name=name)
        if existing is not None:
            continue
        await crud_payment_status.create_draft(
            session=session,
            data=PaymentStatusCreate(name=name, description=description),
            user=None,
        )


async def _seed_manual_payment_methods(session: AsyncSession) -> None:
    methods = (
        {
            "name": "Chèque",
            "description": "Paiement par chèque, validé manuellement à réception.",
            "provider_code": "manual_check",
            "sort_order": 80,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Virement bancaire",
            "description": "Paiement par virement bancaire, validé manuellement à réception.",
            "provider_code": "manual_transfer",
            "sort_order": 90,
            "requires_admin_validation": True,
            "requires_document_upload": False,
        },
        {
            "name": "Bon de commande",
            "description": (
                "Paiement sur bon de commande signé. Le client téléverse "
                "son BC et notre équipe valide la commande après vérification."
            ),
            "provider_code": "po_public",
            "sort_order": 100,
            "requires_admin_validation": True,
            "requires_document_upload": True,
        },
    )

    for spec in methods:
        statement = select(PaymentMethod).where(
            PaymentMethod.provider_code == spec["provider_code"]
        )
        result = await session.exec(statement)
        if result.first() is not None:
            continue

        await crud_payment_method.create_draft(
            session=session,
            data=PaymentMethodCreate(
                name=spec["name"],
                description=spec["description"],
                provider_code=spec["provider_code"],
                requires_admin_validation=spec["requires_admin_validation"],
                requires_document_upload=spec["requires_document_upload"],
                sort_order=spec["sort_order"],
                fee=Decimal("0.00"),
            ),
            user=None,
        )


async def initial_data(session: AsyncSession) -> None:
    await _seed_payment_statuses(session)
    await _seed_manual_payment_methods(session)
