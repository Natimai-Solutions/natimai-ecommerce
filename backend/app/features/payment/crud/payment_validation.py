import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment_validation import (
    PaymentValidation,
    PaymentValidationCreate,
    PaymentValidationUpdate,
)


class PaymentValidationCrud(
    CrudBase[PaymentValidation, PaymentValidationCreate, PaymentValidationUpdate]
):
    async def list_for_payment(
        self,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
    ) -> list[PaymentValidation]:
        statement = (
            select(self.model)
            .where(self.model.payment_id == payment_id)
            .order_by(col(self.model.created_at).asc())
        )
        result = await session.exec(statement)
        return list(result.all())


crud_payment_validation = PaymentValidationCrud(
    model=PaymentValidation,
    schema_create=PaymentValidationCreate,
    schema_update=PaymentValidationUpdate,
    order_by=PaymentValidation.created_at,
)
