import uuid

from sqlmodel import select
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
                self.model.is_admin_active.is_(True),
                self.model.is_active.is_(True),
            )
            .offset(skip)
            .limit(limit)
            .order_by(self.model.created_at.desc())
        )
        exec_result = await session.exec(statement)
        return exec_result.all()

    async def get_by_payzen_trans_id(
        self,
        session: AsyncSession,
        *,
        payzen_trans_id: str,
    ) -> PaymentLog | None:
        """Get a payment log by Payzen transaction ID."""
        statement = select(self.model).where(
            self.model.payzen_trans_id == payzen_trans_id,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()


crud_payment_log = PaymentLogCrud(
    model=PaymentLog,
    schema_create=PaymentLogCreate,
    schema_update=PaymentLogUpdate,
    order_by=PaymentLog.created_at,
)
