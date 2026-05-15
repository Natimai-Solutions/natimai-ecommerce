import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment_log import (
    PaymentLog,
    PaymentLogCreate,
    PaymentLogUpdate,
)


class PaymentLogCrud(CrudBase[PaymentLog, PaymentLogCreate, PaymentLogUpdate]):
    async def get_by_payment_id(
        self,
        session: AsyncSession,
        *,
        payment_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PaymentLog]:
        """Get all logs for a specific payment."""
        statement = (
            select(self.model)
            .where(
                self.model.payment_id == payment_id,
                col(self.model.is_admin_active).is_(True),
                col(self.model.is_active).is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(col(self.model.created_at).desc())
        )
        exec_result = await session.exec(statement)
        return list(exec_result.all())

    async def get_by_provider_reference(
        self,
        session: AsyncSession,
        *,
        provider_reference: str,
    ) -> PaymentLog | None:
        """Get a payment log by provider transaction reference."""
        statement = select(self.model).where(
            self.model.provider_reference == provider_reference,
            col(self.model.is_admin_active).is_(True),
            col(self.model.is_active).is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()


crud_payment_log = PaymentLogCrud(
    model=PaymentLog,
    schema_create=PaymentLogCreate,
    schema_update=PaymentLogUpdate,
    order_by=col(PaymentLog.created_at),
)
