"""Which payments wait for an admin decision (« Validation paiements »).

Manual payments (cheque, transfer…) and document-validated ones (purchase
order) stay in one of the statuses below until an admin approves or rejects
them. The admin list and the dashboard counter share this definition.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.payment.crud.payment_status import crud_payment_status
from app.features.payment.models.payment import Payment
from app.features.payment.providers.document_validated import (
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_UNDER_REVIEW,
)
from app.features.payment.providers.manual import MANUAL_STATUS_AWAITING_VALIDATION
from app.features.payment.services.document_payment import DOCUMENT_PROVIDER_CODES

PENDING_VALIDATION_STATUS_NAMES: tuple[str, ...] = (
    MANUAL_STATUS_AWAITING_VALIDATION,
    DOCUMENT_STATUS_DOCUMENT_UPLOADED,
    DOCUMENT_STATUS_UNDER_REVIEW,
)


async def pending_validation_conditions(session: AsyncSession) -> list[Any] | None:
    """WHERE clauses selecting the payments awaiting manual/document validation.

    ``None`` when none of the pending statuses exists yet (fresh database):
    nothing can be waiting, the caller can skip its query.
    """
    status_ids: list[uuid.UUID] = []
    for name in PENDING_VALIDATION_STATUS_NAMES:
        status = await crud_payment_status.get_by_name(session, name=name)
        if status is not None:
            status_ids.append(status.id)
    if not status_ids:
        return None

    manual_or_document_provider = col(Payment.provider_code).startswith(
        "manual_"
    ) | col(Payment.provider_code).in_(list(DOCUMENT_PROVIDER_CODES))
    return [
        col(Payment.payment_status_id).in_(status_ids),
        manual_or_document_provider,
        col(Payment.is_active).is_(True),
        col(Payment.is_admin_active).is_(True),
    ]
