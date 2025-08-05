from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.base.crud import CrudBase
from app.api.payment.model.payment import (
    Payment,
    PaymentCreate,
    PaymentUpdate,
)


class PaymentCrud(CrudBase[Payment, PaymentCreate, PaymentUpdate]):
    async def get_random_payments(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> list[Payment]:
        statement = (
            select(Payment)
            .where(
                Payment.is_admin_active.is_(True),
                Payment.is_active.is_(True),
            )
            .order_by(func.random())
        )

        if limit > 0:
            statement = statement.limit(limit)

        result = await session.exec(statement)

        return result.all()


crud_payment = PaymentCrud(
    model=Payment,
    create_model=PaymentCreate,
    update_model=PaymentUpdate,
    order_by=Payment.created_at,
)
