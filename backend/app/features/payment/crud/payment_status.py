from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.payment.models.payment_status import (
    PaymentStatus,
    PaymentStatusCreate,
    PaymentStatusUpdate,
)


class PaymentStatusCrud(CrudBase[PaymentStatus, PaymentStatusCreate, PaymentStatusUpdate]):
    async def get_by_name(
        self,
        session: AsyncSession,
        *,
        name: str,
    ) -> PaymentStatus | None:
        """Get payment status by name."""
        statement = select(self.model).where(
            self.model.name == name,
            self.model.is_admin_active.is_(True),
            self.model.is_active.is_(True),
        )
        exec_result = await session.exec(statement)
        return exec_result.first()


crud_payment_status = PaymentStatusCrud(
    model=PaymentStatus,
    schema_create=PaymentStatusCreate,
    schema_update=PaymentStatusUpdate,
    order_by=PaymentStatus.created_at,
)
